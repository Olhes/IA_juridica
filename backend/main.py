from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
import uvicorn
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional
import json
import logging
import uuid
from datetime import datetime, timezone
from dotenv import load_dotenv

from utils.console import configure_console_output

BASE_DIR = Path(__file__).resolve().parent
configure_console_output()
load_dotenv(BASE_DIR / ".env")

# Módulos del sistema
from config.settings import settings
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from security import (
    Principal,
    client_ip_key,
    issue_session,
    limiter,
    principal_from_request,
    require_principal,
    set_session_cookie,
    verify_admin_api_key,
)
from ingestion.pipeline import LegalIngestionPipeline
from modules.rag.services.lightrag_engine import LegalRAGEngine
from agents.pydantic_agents import LegalAgent
from context.context_engineering import ContextEngineer
from database.redis_adapter import redis_adapter
from modules.chat.services.chat_service import chat_service
from modules.chat.controllers.chat_routes import router as chat_router

# ── Módulos de validación y optimización ──────────────────────────────
from modules.validation.services.response_validator import ResponseValidator, ValidationConfig
from optimization.llm_optimizer import LLMOptimizer
# ─────────────────────────────────────────────────────────────────────────────


DOCS_DIR = BASE_DIR / "docs"
RAW_PDFS_DIR = DOCS_DIR / "raw_pdfs"
PROCESSED_DIR = DOCS_DIR / "processed"
KNOWLEDGE_GRAPH_DIR = DOCS_DIR / "knowledge_graph"

logger = logging.getLogger("ia_juridica.api")


def _log_failure(event: str, error: Exception, request: Optional[Request] = None) -> None:
    request_id = getattr(getattr(request, "state", None), "request_id", "unknown")
    logger.error(
        "%s request_id=%s error_type=%s",
        event,
        request_id,
        type(error).__name__,
    )


def _get_pdf_processor(app: FastAPI):
    processor = getattr(app.state, "pdf_processor", None)
    if processor is None:
        from ingestion.docling_processor import LegalPDFProcessor

        processor = LegalPDFProcessor()
        app.state.pdf_processor = processor
    return processor


def _get_evaluation_suite(app: FastAPI):
    if not settings.EVALUATION_ENABLED:
        return None
    suite = getattr(app.state, "evaluation_suite", None)
    if suite is None:
        from evaluation.deepeval_tests import LegalEvaluationSuite

        suite = LegalEvaluationSuite()
        app.state.evaluation_suite = suite
    return suite


# ── Modelos de request/response ────────────────────────────────────────────────


class LegalQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(..., min_length=1, max_length=8000)
    language: str = Field(default="spanish")
    context: Optional[Dict[str, Any]] = None
    conversation_id: Optional[str] = None


class PDFReportRequest(BaseModel):
    query: str = Field(..., min_length=1)
    response: Dict[str, Any]

def _ndjson_event(payload: Dict[str, Any]) -> str:
    """Serializa eventos NDJSON manejando datetime/enums/modelos pydantic."""
    serializable = jsonable_encoder(payload)
    return json.dumps(serializable, ensure_ascii=False) + "\n"


def _extract_response_text(response_payload: Any, language: str) -> str:
    if not isinstance(response_payload, dict):
        return str(response_payload or "")

    field_order = (
        ("respuesta_quechua", "quechua", "respuesta_espanol", "spanish", "answer")
        if language == "quechua"
        else ("respuesta_espanol", "spanish", "answer", "respuesta_quechua", "quechua")
    )
    for field in field_order:
        value = response_payload.get(field)
        if isinstance(value, str) and value.strip():
            return value
    return ""


async def _persist_assistant_response(
    conversation_id: Optional[str],
    owner_id: str,
    response_payload: Any,
    language: str,
    metadata: Dict[str, Any],
) -> None:
    if not conversation_id:
        return

    content = _extract_response_text(response_payload, language)
    if not content:
        print("Skipping empty assistant response persistence")
        return

    try:
        from models.chat_models import MessageCreate, MessageRole

        await chat_service.add_message(
            conversation_id=conversation_id,
            user_id=owner_id,
            message_data=MessageCreate(
                content=content,
                role=MessageRole.ASSISTANT,
                language=language,
                metadata=metadata,
            ),
        )
    except Exception as error:
        _log_failure("assistant_persistence_failed", error)

# ── Lifespan ───────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Inicializando IA Jurídica v2.1...")

    configuration = settings.validate_configuration()
    if not configuration["valid"]:
        raise RuntimeError("Invalid configuration: " + "; ".join(configuration["issues"]))

    # Inicializar Redis adapter
    try:
        await redis_adapter.initialize()
        print("Redis adapter inicializado correctamente")
    except Exception:
        print("Error inicializando Redis")
        print("Continuando sin Redis...")
    
    # Inicializar chat service
    try:
        await chat_service.initialize()
        print("Chat service inicializado correctamente")
    except Exception:
        print("Error inicializando chat service")
        print("Continuando sin chat persistente...")

    if not hasattr(app.state, "rag_engine"):
        RAW_PDFS_DIR.mkdir(parents=True, exist_ok=True)
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        KNOWLEDGE_GRAPH_DIR.mkdir(parents=True, exist_ok=True)

        app.state.rag_engine = LegalRAGEngine()

        await app.state.rag_engine.initialize_storages()

        loaded = await app.state.rag_engine.load_processed_documents(str(PROCESSED_DIR))
        print(
            f"Documentos en memoria: {len(app.state.rag_engine.documents)} ({loaded} nuevos)"
        )

        app.state.ingestion_pipeline = LegalIngestionPipeline(
            rag_engine=app.state.rag_engine
        )
        app.state.legal_agent = LegalAgent()
        app.state.context_engineer = ContextEngineer()

        # ── Componentes de validación y optimización [NUEVO] ──────────────────
        validation_config = ValidationConfig(
            hallucination_threshold=settings.EVALUATION_THRESHOLD,  # 0.7 por defecto
            cross_check_threshold=0.55,
            min_confidence_score=0.30,
            max_self_correction_retries=2,
            enable_cross_check=True,
            enable_self_correction=True,
            enable_cultural_validation=True,
        )
        app.state.response_validator = ResponseValidator(
            rag_engine=app.state.rag_engine,
            cohere_client=app.state.legal_agent.cohere_client,
            context_engineer=app.state.context_engineer,
            config=validation_config,
        )
        app.state.llm_optimizer = LLMOptimizer(
            cache_ttl_seconds=settings.CACHE_TTL,
            max_cache_size=settings.CACHE_MAX_SIZE,
        )
        print("ResponseValidator y LLMOptimizer inicializados")
        # ─────────────────────────────────────────────────────────────────────

        app.state.evaluation_suite = None

        print("Componentes inicializados correctamente")
    else:
        print("Componentes ya inicializados, saltando...")

    yield

    print("Cerrando IA Jurídica...")
    
    # Cerrar Redis adapter
    try:
        await redis_adapter.close()
        print("Redis adapter cerrado correctamente")
    except Exception:
        print("Error cerrando Redis")


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="IA Jurídica - Sistema Legal Bilingüe",
    description="Asistente legal especializado con RAG avanzado y validación anti-alucinación",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.docs_enabled() else None,
    redoc_url="/redoc" if settings.docs_enabled() else None,
    openapi_url="/openapi.json" if settings.docs_enabled() else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def request_context(request: Request, call_next):
    supplied_id = request.headers.get("X-Request-ID", "")
    request_id = supplied_id if supplied_id.isascii() and len(supplied_id) <= 64 else uuid.uuid4().hex
    request.state.request_id = request_id
    try:
        response = await call_next(request)
    except Exception as error:
        _log_failure("request_failed", error, request)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
        )
    response.headers["X-Request-ID"] = request_id
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

# Registrar rutas de chat persistente
app.include_router(chat_router)


# ── Endpoints ──────────────────────────────────────────────────────────────────


@app.post("/session/bootstrap")
@limiter.limit(settings.SESSION_BOOTSTRAP_RATE_LIMIT, key_func=client_ip_key)
async def bootstrap_session(request: Request, response: Response):
    try:
        existing = principal_from_request(request)
        token, principal = issue_session(existing.id if existing else None)
        set_session_cookie(response, token, principal)
        return {
            "principal_id": principal.id,
            "expires_at": datetime.fromtimestamp(principal.expires_at, timezone.utc).isoformat(),
        }
    except Exception as e:
        print(f"Error in session bootstrap: {e}")
        raise HTTPException(status_code=500, detail="Failed to create session")


@app.get("/")
async def root():
    return {
        "message": "IA Jurídica API v2.1 - Sistema Legal con Docling, RAG y Validación Anti-Alucinación"
    }


@app.get("/health")
async def health_check():
    """Health check que incluye estado del pipeline de validación."""
    components = {}

    components["cohere"] = "ready" if settings.COHERE_API_KEY else "not_configured"

    try:
        rag = getattr(app.state, "rag_engine", None)
        if rag and rag._storages_initialized:
            components["lightrag"] = "ready"
        elif rag:
            components["lightrag"] = "not_initialized"
        else:
            components["lightrag"] = "unavailable"
    except Exception:
        components["lightrag"] = "error"

    try:
        agent = getattr(app.state, "legal_agent", None)
        if agent:
            from agents.pydantic_agents import PYDANTIC_AI_AVAILABLE

            components["pydantic_ai"] = "ready" if PYDANTIC_AI_AVAILABLE else "fallback"
        else:
            components["pydantic_ai"] = "unavailable"
    except Exception:
        components["pydantic_ai"] = "error"

    components["context_engineer"] = (
        "ready" if getattr(app.state, "context_engineer", None) else "unavailable"
    )
    # ── Estado de validación [NUEVO] ───────────────────────────────────────────
    components["response_validator"] = (
        "ready" if getattr(app.state, "response_validator", None) else "unavailable"
    )
    components["llm_optimizer"] = (
        "ready" if getattr(app.state, "llm_optimizer", None) else "unavailable"
    )
    # ── Health check de Redis ──────────────────────────────────────────────────
    try:
        redis_health = await redis_adapter.health_check()
        components["redis"] = redis_health.get("status", "unknown")
    except Exception:
        components["redis"] = "error"
    # ── Health check de Chat Service ──────────────────────────────────────────
    try:
        db_health = await chat_service.db.health_check()
        components["postgresql"] = db_health.get("status", "unknown")
    except Exception:
        components["chat_service"] = "error"

    critical_ok = all(
        components.get(c) in ("ready", "fallback")
        for c in ("cohere", "lightrag", "pydantic_ai")
    ) and components.get("postgresql") == "healthy"

    return {
        "status": "healthy" if critical_ok else "degraded",
        "components": components,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.post("/upload-pdf")
@limiter.limit(settings.ADMIN_RATE_LIMIT)
async def upload_pdf(
    request: Request,
    file: UploadFile = File(...),
    _auth: bool = Depends(verify_admin_api_key),
):
    """Sube y procesa un PDF legal con Docling."""
    raw_path: Optional[Path] = None
    processed_path: Optional[Path] = None
    try:
        original_name = (file.filename or "upload.pdf").replace("\\", "/").rsplit("/", 1)[-1]
        original_name = "".join(char for char in original_name if char.isprintable())[:255]
        if Path(original_name).suffix.lower() != ".pdf":
            raise HTTPException(400, "Only PDF files are allowed")
        if file.content_type != "application/pdf":
            raise HTTPException(400, "Invalid PDF media type")

        raw_directory = RAW_PDFS_DIR.resolve()
        raw_directory.mkdir(parents=True, exist_ok=True)
        server_name = f"{uuid.uuid4().hex}.pdf"
        raw_path = (raw_directory / server_name).resolve()
        if raw_path.parent != raw_directory:
            raise HTTPException(400, "Invalid upload path")

        total_size = 0
        first_chunk = True
        with raw_path.open("xb") as buffer:
            while chunk := await file.read(1024 * 1024):
                total_size += len(chunk)
                if total_size > settings.MAX_FILE_SIZE:
                    raise HTTPException(413, "PDF exceeds maximum allowed size")
                if first_chunk:
                    if not chunk.startswith(b"%PDF-"):
                        raise HTTPException(400, "Invalid PDF signature")
                    first_chunk = False
                buffer.write(chunk)
        if first_chunk:
            raise HTTPException(400, "Empty PDF file")

        pdf_processor = _get_pdf_processor(app)
        processed_content = await pdf_processor.process_pdf(str(raw_path))

        processed_directory = PROCESSED_DIR.resolve()
        processed_directory.mkdir(parents=True, exist_ok=True)
        processed_path = processed_directory / f"{raw_path.stem}.md"
        with processed_path.open("x", encoding="utf-8") as f:
            f.write(processed_content)

        await app.state.rag_engine.add_document(
            processed_content,
            {
                "filename": server_name,
                "original_filename": original_name,
                "title": original_name,
                "document_type": "legal_pdf",
                "source": "upload-pdf",
            },
            server_name,
        )

        # Actualizar el CrossChecker con el nuevo documento [NUEVO]
        if hasattr(app.state, "response_validator"):
            app.state.response_validator.cross_checker.update_documents(
                app.state.rag_engine.documents
            )

        return {
            "success": True,
            "filename": server_name,
            "original_filename": original_name,
            "message": "PDF procesado correctamente con Docling",
        }
    except HTTPException:
        if raw_path:
            raw_path.unlink(missing_ok=True)
        if processed_path:
            processed_path.unlink(missing_ok=True)
        raise
    except Exception as error:
        if raw_path:
            raw_path.unlink(missing_ok=True)
        if processed_path:
            processed_path.unlink(missing_ok=True)
        _log_failure("pdf_upload_failed", error, request)
        raise HTTPException(500, "PDF processing failed")
    finally:
        await file.close()


@app.post("/batch-process")
@limiter.limit(settings.ADMIN_RATE_LIMIT)
async def batch_process_pdfs(
    request: Request, _auth: bool = Depends(verify_admin_api_key)
):
    """Procesa todos los PDFs del directorio raw_pdfs."""
    try:
        results = await app.state.ingestion_pipeline.process_all_pdfs()
        return {
            "success": True,
            "processed": results["processed_count"],
            "failed": results["failed_count"],
            "details": results["details"],
        }
    except Exception as error:
        _log_failure("batch_processing_failed", error, request)
        raise HTTPException(500, "Batch processing failed")


@app.post("/legal-query")
@limiter.limit(settings.LLM_RATE_LIMIT)
async def legal_query(
    request: Request,
    payload: LegalQueryRequest,
    principal: Principal = Depends(require_principal),
):
    """
    Procesa una consulta legal con RAG + Rerank + Context Engineering
    + LLM (Cohere) + Pipeline de Validación Anti-Alucinación.

    Response incluye:
      - response: respuesta del LLM (posiblemente corregida)
      - validation: informe de calidad de la respuesta
      - sources: fuentes RAG usadas
    """
    try:
        query = payload.query.strip()
        language = payload.language
        optimizer: LLMOptimizer = app.state.llm_optimizer

        # ── Caché semántico: verificar antes de llamar al LLM ── [NUEVO]
        cache_key = f"{query}|{language}"
        cached_result = optimizer.get_cached(cache_key)
        if cached_result:
            cached_payload = cached_result if isinstance(cached_result, dict) else {}
            return {
                "success": True,
                "query": query,
                "language": language,
                "cached": True,
                **cached_payload,
            }

        # 1. Búsqueda RAG con reranking
        rag_result = await app.state.rag_engine.query_with_rerank(query)

        # 2. Construir prompt enriquecido
        documents = rag_result.get("documents", [])
        enriched_prompt, enriched_context = (
            app.state.context_engineer.build_legal_prompt(
                query=query,
                documents=documents,
                language=language,
            )
        )

        # 3. Generar respuesta con Cohere LLM
        response = await app.state.legal_agent.respond_general(
            query=query,
            context=rag_result,
            language=language,
            enriched_prompt=enriched_prompt,
        )

        if hasattr(response, "model_dump"):
            response_payload = response.model_dump()
        elif hasattr(response, "dict"):
            response_payload = response.dict()
        else:
            response_payload = response

        # Tracking de tokens ── [NUEVO]
        optimizer.track(enriched_prompt or query, str(response_payload))

        # 4. Pipeline de validación anti-alucinación ── [NUEVO]
        validated = await app.state.response_validator.validate(
            response_data=response_payload,
            rag_result=rag_result,
            query=query,
            language=language,
            enriched_context=enriched_context,
        )

        # Preparar payload final
        final_response = validated.answer_data
        validation_meta = validated.validation_report.model_dump()

        result_payload = {
            "response": final_response,
            "sources": validated.sources,
            "validation": validation_meta,
            "metadata": {
                "rerank_scores": rag_result.get("rerank_scores", []),
                "retrieval_method": rag_result.get("method", "unknown"),
                "total_candidates": rag_result.get("total_candidates", 0),
                "enriched_context": {
                    "location": enriched_context.get("detected_location"),
                    "legal_topic": enriched_context.get("legal_topic"),
                    "urgency": enriched_context.get("urgency_level"),
                },
                "optimizer_stats": optimizer.get_session_stats(),
            },
        }

        # Cachear respuesta válida ── [NUEVO]
        if validated.is_reliable:
            optimizer.cache_response(cache_key, result_payload)

        return {
            "success": True,
            "query": query,
            "language": language,
            "cached": False,
            **result_payload,
        }

    except Exception as error:
        _log_failure("legal_query_failed", error, request)
        raise HTTPException(500, "Legal query failed")


@app.post("/legal-query-stream")
@limiter.limit(settings.LLM_RATE_LIMIT)
async def legal_query_stream(
    request: Request,
    payload: LegalQueryRequest,
    principal: Optional[Principal] = Depends(lambda: None),
):
    """Stream NDJSON con chunks + payload final validado (1 sola llamada).
    
    Si se proporciona conversation_id, guarda los mensajes sólo para su propietario.
    """
    print(f"DEBUG legal_query_stream: principal={principal}, payload={payload}")
    
    # Temporary fix for debugging: use a default principal ID when auth is disabled
    principal_id = principal.id if principal else "debug-user"
    
    query = payload.query.strip()
    language = payload.language
    conversation_id = payload.conversation_id
    optimizer: LLMOptimizer = app.state.llm_optimizer
    cache_key = f"{query}|{language}"
    
    # Detectar idioma y traducir si es quechua
    from modules.language.services.language_detector import LanguageDetector
    from modules.language.services.translation_service import TranslationService
    
    detector = LanguageDetector()
    detected_language = detector.detect_language(query)
    
    query_for_processing = query
    original_language = language
    
    if detected_language == "qu" or language == "quechua":
        translation_service = TranslationService()
        translation_result = await translation_service.translate(
            text=query,
            source_lang="qu",
            target_lang="es"
        )
        
        if translation_result.get("success"):
            query_for_processing = translation_result["translated_text"]
            original_language = "quechua"
        else:
            query_for_processing = query
            original_language = "quechua"
    
    # Usar query_for_processing para el cache y procesamiento
    cache_key = f"{query_for_processing}|{language}"

    # Guardar mensaje del usuario si se proporciona conversation_id
    if conversation_id:
        if not await chat_service.get_conversation(conversation_id, principal_id):
            raise HTTPException(status_code=404, detail="Conversation not found")
        try:
            from models.chat_models import MessageCreate, MessageRole
            await chat_service.add_message(
                conversation_id=conversation_id,
                user_id=principal_id,
                message_data=MessageCreate(
                    content=query,
                    role=MessageRole.USER,
                    language=language
                )
            )
        except ValueError:
            raise HTTPException(status_code=404, detail="Conversation not found")

    cached_result = optimizer.get_cached(cache_key)
    if cached_result:
        cached_payload = cached_result if isinstance(cached_result, dict) else {}
        response_payload = jsonable_encoder(cached_payload.get("response", {}))
        cached_text = _extract_response_text(response_payload, language)
        await _persist_assistant_response(
            conversation_id,
            principal_id,
            response_payload,
            language,
            {
                "sources": cached_payload.get("sources", []),
                "validation": cached_payload.get("validation", {}),
            },
        )

        async def cached_stream_generator():
            if cached_text:
                yield _ndjson_event({"type": "chunk", "delta": cached_text})
            yield _ndjson_event(
                {
                    "type": "final",
                    "data": {
                        "success": True,
                        "query": query,
                        "language": language,
                        "cached": True,
                        **cached_payload,
                    },
                }
            )

        return StreamingResponse(
            cached_stream_generator(),
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    async def stream_generator():
        try:
            streamed_text = ""

            rag_result = await app.state.rag_engine.query_with_rerank(query_for_processing)
            documents = rag_result.get("documents", [])
            enriched_prompt, enriched_context = (
                app.state.context_engineer.build_legal_prompt(
                    query=query_for_processing,
                    documents=documents,
                    language=language,
                )
            )

            async for chunk in app.state.legal_agent.stream_general_text(
                query_for_processing,
                rag_result,
                language,
                enriched_prompt=enriched_prompt,
            ):
                if chunk:
                    streamed_text += chunk
                    yield _ndjson_event({"type": "chunk", "delta": chunk})

            response = app.state.legal_agent.build_general_response_from_text(
                text=streamed_text,
                query=query_for_processing,
            )

            if hasattr(response, "model_dump"):
                response_payload = response.model_dump()
            elif hasattr(response, "dict"):
                response_payload = response.dict()
            else:
                response_payload = response

            optimizer.track(enriched_prompt or query_for_processing, str(response_payload))

            validated = await app.state.response_validator.validate(
                response_data=response_payload,
                rag_result=rag_result,
                query=query_for_processing,
                language=language,
                enriched_context=enriched_context,
            )

            final_response = validated.answer_data
            validation_meta = validated.validation_report.model_dump()
            
            # Traducir respuesta de español a quechua si el idioma original era quechua
            if original_language == "quechua":
                translation_service = TranslationService()
                
                # Extraer el texto de respuesta
                if isinstance(final_response, dict):
                    response_text = _extract_response_text(final_response, "spanish")
                else:
                    response_text = str(final_response)
                
                # Truncamiento forzado a 1000 caracteres (Google Translate maneja mejor que NLLB-200)
                MAX_RESPONSE_LENGTH = 1000
                if len(response_text) > MAX_RESPONSE_LENGTH:
                    response_text = response_text[:MAX_RESPONSE_LENGTH] + "..."
                
                translation_result = await translation_service.translate(
                    text=response_text,
                    source_lang="es",
                    target_lang="qu"
                )
                
                if translation_result.get("success"):
                    translated_text = translation_result["translated_text"]
                    # Actualizar la respuesta con el texto traducido
                    if isinstance(final_response, dict):
                        final_response["answer"] = translated_text
                        final_response["respuesta_quechua"] = translated_text
                    else:
                        final_response = translated_text

            result_payload = {
                "response": final_response,
                "sources": validated.sources,
                "validation": validation_meta,
                "metadata": {
                    "rerank_scores": rag_result.get("rerank_scores", []),
                    "retrieval_method": rag_result.get("method", "unknown"),
                    "total_candidates": rag_result.get("total_candidates", 0),
                    "enriched_context": {
                        "location": enriched_context.get("detected_location"),
                        "legal_topic": enriched_context.get("legal_topic"),
                        "urgency": enriched_context.get("urgency_level"),
                    },
                    "optimizer_stats": optimizer.get_session_stats(),
                },
            }

            if validated.is_reliable:
                optimizer.cache_response(cache_key, result_payload)

            await _persist_assistant_response(
                conversation_id,
                principal_id,
                final_response,
                language,
                {"sources": validated.sources, "validation": validation_meta},
            )

            yield _ndjson_event(
                {
                    "type": "final",
                    "data": {
                        "success": True,
                        "query": query,
                        "language": language,
                        "cached": False,
                        **result_payload,
                    },
                }
            )
        except Exception as stream_error:
            _log_failure("legal_query_stream_failed", stream_error, request)
            yield _ndjson_event(
                {
                    "type": "error",
                    "error": "Legal query stream failed",
                }
            )

    return StreamingResponse(
        stream_generator(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/generate-pdf-report")
async def generate_pdf_report(
    payload: PDFReportRequest,
    principal: Principal = Depends(require_principal),
):
    """Genera reporte PDF legal con ReportLab."""
    try:
        from utils.pdf_generator import generate_legal_pdf_bytes

        pdf_bytes = generate_legal_pdf_bytes(
            query=payload.query,
            response_data=payload.response,
        )

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="reporte_legal.pdf"',
                "Cache-Control": "no-store",
            },
        )
    except ImportError:
        raise HTTPException(503, "PDF generation unavailable")
    except Exception as error:
        _log_failure("pdf_generation_failed", error)
        raise HTTPException(500, "PDF generation failed")


@app.get("/knowledge-graph")
async def get_knowledge_graph(_auth: bool = Depends(verify_admin_api_key)):
    try:
        graph_data = await app.state.rag_engine.get_knowledge_graph()
        return {"success": True, "graph": graph_data}
    except Exception as error:
        _log_failure("knowledge_graph_read_failed", error)
        raise HTTPException(500, "Failed to get knowledge graph")


@app.post("/evaluate-system")
@limiter.limit(settings.ADMIN_RATE_LIMIT)
async def evaluate_system(
    request: Request, _auth: bool = Depends(verify_admin_api_key)
):
    try:
        evaluation_suite = _get_evaluation_suite(app)
        if evaluation_suite is None:
            raise HTTPException(503, "Evaluación deshabilitada por configuración")
        evaluation_results = await evaluation_suite.run_full_evaluation()
        return {"success": True, "results": evaluation_results}
    except HTTPException:
        raise
    except Exception as error:
        _log_failure("evaluation_failed", error, request)
        raise HTTPException(500, "Evaluation failed")


@app.get("/documents")
async def list_documents(_auth: bool = Depends(verify_admin_api_key)):
    try:
        docs = await app.state.rag_engine.list_documents()
        return {"success": True, "documents": docs}
    except Exception as error:
        _log_failure("document_listing_failed", error)
        raise HTTPException(500, "Failed to list documents")


# ── Endpoint de estadísticas de validación ────────────────────────────


@app.get("/validation-stats")
async def get_validation_stats(_auth: bool = Depends(verify_admin_api_key)):
    """
    Retorna estadísticas del pipeline de validación y uso del optimizador.
    Útil para monitoreo y ajuste de umbrales.
    """
    try:
        optimizer: LLMOptimizer = app.state.llm_optimizer
        rag_stats = app.state.rag_engine.get_stats()

        return {
            "success": True,
            "optimizer": optimizer.get_session_stats(),
            "rag_engine": rag_stats,
            "validation_config": {
                "hallucination_threshold": app.state.response_validator.config.hallucination_threshold,
                "cross_check_threshold": app.state.response_validator.config.cross_check_threshold,
                "min_confidence_score": app.state.response_validator.config.min_confidence_score,
                "self_correction_retries": app.state.response_validator.config.max_self_correction_retries,
            },
        }
    except Exception as error:
        _log_failure("validation_stats_failed", error)
        raise HTTPException(500, "Stats failed")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.is_development(),
        log_level="info",
    )
