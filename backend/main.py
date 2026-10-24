from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
import uvicorn
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any, Dict, Literal, Optional
import json
import logging
import asyncio
import uuid
from datetime import datetime, timezone
from dotenv import load_dotenv

from utils.console import configure_console_output

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent  # Subir a la raíz del proyecto
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
from ingestion.source_evidence import persist_source_evidence
from modules.rag.services.lightrag_engine import LegalRAGEngine
from agents.pydantic_agents import LegalAgent
from context.context_engineering import ContextEngineer
from database.redis_adapter import redis_adapter
from modules.chat.services.chat_service import chat_service
from modules.chat.routes.chat_routes import router as chat_router
from modules.auth.routes.auth_routes import router as auth_router
from modules.voice.services.tts_service import TTSService

# ── Módulos de validación y optimización ──────────────────────────────
from modules.validation.services.response_validator import (
    ResponseValidator,
    ValidationConfig,
)
from optimization.llm_optimizer import LLMOptimizer
from optimization.query_cache import answer_cache_key
from services.legal_queries import answer_query
from services.legal_stream import stream_legal_query
from services.stream_guard import guard_stream
from services.stream_telemetry import StreamTelemetry, stream_metrics
from services.feedback_store import FeedbackIn, FeedbackStore
from services.quality_access import require_quality_admin
from services.quality_reports import admin_overview, load_published
from context.conversation_prompt import bounded_history, with_conversation
from models.request_types import NonBlankMessage, SupportedLanguage, RequestContext
from database.postgres_adapter_final import DatabaseUnavailableError

# ─────────────────────────────────────────────────────────────────────────────


DOCS_DIR = PROJECT_ROOT / "docs"
RAW_PDFS_DIR = DOCS_DIR / "raw_pdfs"
PROCESSED_DIR = DOCS_DIR / "processed"
KNOWLEDGE_GRAPH_DIR = DOCS_DIR / "knowledge_graph"

logger = logging.getLogger("ia_juridica.api")


def _log_failure(
    event: str, error: Exception, request: Optional[Request] = None
) -> None:
    request_id = getattr(getattr(request, "state", None), "request_id", "unknown")
    logger.error(
        "%s request_id=%s error_type=%s",
        event,
        request_id,
        type(error).__name__,
    )


def _get_document_processor(app: FastAPI):
    processor = getattr(app.state, "document_processor", None)
    if processor is None:
        from ingestion.docling_processor import LegalDocumentProcessor

        processor = LegalDocumentProcessor()
        app.state.document_processor = processor
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
    query: NonBlankMessage
    language: SupportedLanguage = "spanish"
    context: Optional[RequestContext] = None
    conversation_id: Optional[str] = None


async def _prepare_query_context(payload, owner_id, mode):
    history = []
    if payload.conversation_id:
        if not await chat_service.get_conversation(payload.conversation_id, owner_id):
            raise HTTPException(404, "Conversation not found")
        messages = await chat_service.get_conversation_messages(
            payload.conversation_id, owner_id, limit=12
        )
        history = bounded_history(messages)
    try:
        with_conversation("", history, payload.context)
    except ValueError:
        raise HTTPException(422, "Conversation context exceeds the prompt budget")
    engine = getattr(app.state, "rag_engine", None)
    revision_fn = getattr(engine, "get_cache_revision", None)
    revision = revision_fn() if callable(revision_fn) else None
    key = None
    if isinstance(revision, str) and revision:
        key = answer_cache_key(
            payload.query,
            payload.language,
            owner_id,
            payload.context,
            history,
            payload.conversation_id,
            revision,
            mode,
        )
    return key, history


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
    except DatabaseUnavailableError:
        raise
    except Exception as error:
        _log_failure("assistant_persistence_failed", error)
        raise HTTPException(503, "Chat persistence unavailable")


# ── Lifespan ───────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"Inicializando IA Jurídica {settings.APP_VERSION}...")

    configuration = settings.validate_configuration()
    if not configuration["valid"]:
        raise RuntimeError(
            "Invalid configuration: " + "; ".join(configuration["issues"])
        )

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

    # Inicializar componentes básicos primero para startup rápido
    if not hasattr(app.state, "rag_engine"):
        RAW_PDFS_DIR.mkdir(parents=True, exist_ok=True)
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        KNOWLEDGE_GRAPH_DIR.mkdir(parents=True, exist_ok=True)

        # Crear instancias pero no inicializar componentes pesados
        app.state.rag_engine = LegalRAGEngine(working_dir=str(KNOWLEDGE_GRAPH_DIR))
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
        print("Componentes básicos inicializados")
        # ─────────────────────────────────────────────────────────────────────

        app.state.evaluation_suite = None

        print("Inicialización básica completada - iniciando servidor...")
    else:
        print("Componentes ya inicializados, saltando...")

    app.state.corpus_state = "loading"
    app.state.corpus_task = asyncio.create_task(load_heavy_components(app.state.rag_engine, PROCESSED_DIR))
    try:
        yield
    finally:
        task = app.state.corpus_task
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        app.state.corpus_state = "stopped"
        finalizer = getattr(getattr(app.state.rag_engine, "rag", None), "finalize_storages", None)
        if callable(finalizer):
            try:
                await finalizer()
            except Exception as error:
                _log_failure("rag_shutdown_failed", error)
        for resource in (chat_service.db, redis_adapter):
            try:
                await resource.close()
            except Exception as error:
                _log_failure("storage_shutdown_failed", error)


async def load_heavy_components(rag_engine, processed_dir):
    """Load corpus once; retry bounded storage failures; never re-ingest on startup."""
    for attempt in range(3):
        try:
            await asyncio.wait_for(rag_engine.initialize_storages(), timeout=60)
            await asyncio.wait_for(rag_engine.load_processed_documents(str(processed_dir)), timeout=120)
            if not rag_engine.documents:
                app.state.corpus_state = "degraded"
            elif settings.NEO4J_ENABLED and not rag_engine._storages_initialized:
                app.state.corpus_state = "degraded"
            else:
                app.state.corpus_state = "ready"
            return
        except asyncio.CancelledError:
            raise
        except Exception as error:
            _log_failure("corpus_load_failed", error)
            if attempt < 2:
                await asyncio.sleep(0.5 * (attempt + 1))
    app.state.corpus_state = "failed"



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
    # Server-owned identifier: never copy user-supplied data into logs.
    request_id = uuid.uuid4().hex
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
    logger.info(
        "request_completed request_id=%s status=%s", request_id, response.status_code
    )
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

# Registrar rutas de chat persistente (DESPUÉS del middleware)
app.include_router(chat_router)
app.include_router(auth_router)


@app.exception_handler(DatabaseUnavailableError)
async def database_unavailable_handler(
    request: Request, error: DatabaseUnavailableError
):
    _log_failure("chat_persistence_unavailable", error, request)
    return JSONResponse(
        status_code=503, content={"detail": "Chat persistence unavailable"}
    )


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
            "expires_at": datetime.fromtimestamp(
                principal.expires_at, timezone.utc
            ).isoformat(),
        }
    except Exception as e:
        print(f"Error in session bootstrap: {e}")
        raise HTTPException(status_code=500, detail="Failed to create session")


@app.get("/")
async def root():
    return {
        "message": f"IA Jurídica API {settings.APP_VERSION} - Sistema Legal con Docling, RAG y Validación Anti-Alucinación"
    }


@app.get("/ready")
async def readiness():
    phase = getattr(app.state, "corpus_state", "unavailable")
    if phase != "ready":
        raise HTTPException(503, "Legal corpus unavailable")
    return {"status": "ready"}


@app.get("/health")
async def health_check():
    """Health check que incluye estado del pipeline de validación."""
    components = {"corpus": getattr(app.state, "corpus_state", "unavailable")}

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
    # ── Comprobación de estado de Redis ────────────────────────────────────────
    try:
        redis_health = await redis_adapter.health_check()
        components["redis"] = redis_health.get("status", "unknown")
    except Exception:
        components["redis"] = "error"
    # ── Comprobación de estado del servicio de chat ────────────────────────────
    try:
        db_health = await chat_service.db.health_check()
        components["postgresql"] = db_health.get("status", "unknown")
    except Exception:
        components["chat_service"] = "error"

    critical_ok = (
        all(
            components.get(c) in ("ready", "fallback")
            for c in ("cohere", "lightrag", "pydantic_ai")
        )
        and components.get("postgresql") == "healthy"
        and components.get("corpus") == "ready"
    )

    return {
        "status": "healthy" if critical_ok else "degraded",
        "components": components,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


class DocumentQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Pregunta sobre el documento")
    language: SupportedLanguage = "spanish"


@app.post("/query-document")
@limiter.limit(settings.LLM_RATE_LIMIT)
async def query_document(
    request: Request,
    file: UploadFile = File(...),
    query: str = Form(...),
    language: SupportedLanguage = Form("spanish"),
    principal: Principal = Depends(require_principal),
):
    """
    Procesa un documento temporalmente (imagen/PDF) y responde preguntas usando Cohere.
    El documento NO se guarda en el RAG permanentemente.
    """
    from ingestion.docling_processor import LegalDocumentProcessor

    temp_path: Optional[Path] = None
    try:
        # Validar archivo
        original_name = (
            (file.filename or "upload").replace("\\", "/").rsplit("/", 1)[-1]
        )
        original_name = "".join(char for char in original_name if char.isprintable())[:255]

        file_ext = Path(original_name).suffix.lower()
        supported_exts = LegalDocumentProcessor.SUPPORTED_IMAGE_FORMATS | LegalDocumentProcessor.SUPPORTED_DOC_FORMATS
        if file_ext not in supported_exts:
            raise HTTPException(
                400,
                f"Formato no soportado: {file_ext}. "
                f"Formatos soportados: PDF, DOCX, PPTX, XLSX, imágenes (PNG, JPEG, TIFF, etc.)"
            )

        # Guardar archivo temporalmente
        temp_dir = BASE_DIR / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"{uuid.uuid4().hex}{file_ext}"

        total_size = 0
        with temp_path.open("xb") as buffer:
            while chunk := await file.read(1024 * 1024):
                total_size += len(chunk)
                if total_size > settings.MAX_FILE_SIZE:
                    raise HTTPException(413, "File exceeds maximum allowed size")
                buffer.write(chunk)

        if total_size == 0:
            raise HTTPException(400, "Empty file")

        # Procesar documento con Docling
        document_processor = LegalDocumentProcessor()
        markdown_content = await document_processor.process_document(
            str(temp_path), write_output=False
        )

        # Preparar prompt para Cohere con el contenido del documento
        from agents.pydantic_agents import LegalAgent

        legal_agent = LegalAgent()

        if not legal_agent.cohere_client:
            raise HTTPException(500, "Cohere client not initialized")

        from agents.pydantic_agents import GLOBAL_SYSTEM_PROMPT, SYSTEM_PROMPT_GUARDRAILS

        system_prompt = f"""{GLOBAL_SYSTEM_PROMPT}

{SYSTEM_PROMPT_GUARDRAILS}

INSTRUCCIONES ESPECÍFICAS PARA ANÁLISIS DE DOCUMENTOS:
1. Analiza el documento proporcionado en formato Markdown
2. Identifica el tipo de documento (ley, reglamento, jurisprudencia, etc.)
3. Extrae y estructura la información relevante: artículos modificados, cambios principales, plazos, entidades involucradas
4. Cita artículos específicos y números de ley cuando sea posible
5. Organiza la respuesta en secciones claras con encabezados
6. Si el documento es una modificación legislativa, explica claramente qué cambia y qué no
7. Mantén el tono profesional y técnico pero accesible

Responde en {language}."""

        user_message = f"""DOCUMENTO:
{markdown_content}

PREGUNTA:
{query}

Responde en {language}."""

        # Llamar a Cohere
        try:
            response = await legal_agent.cohere_client.chat(
                model="command-r-plus-08-2024",
                message=user_message,
                preamble=system_prompt,
                chat_history=[],
                temperature=0.3,
            )
        except AttributeError as e:
            import traceback
            error_details = f"AttributeError: {str(e)}\n{traceback.format_exc()}"
            logging.getLogger("ia_juridica.api").error(f"Cohere client error: {error_details}")
            raise HTTPException(500, f"Cohere client error: {str(e)}")
        except Exception as e:
            import traceback
            error_details = f"Error: {str(e)}\n{traceback.format_exc()}"
            logging.getLogger("ia_juridica.api").error(f"Cohere API error: {error_details}")
            raise HTTPException(500, f"Cohere API error: {str(e)}")

        return {
            "success": True,
            "query": query,
            "response": response.text,
            "language": language,
            "document_type": "image" if file_ext in LegalDocumentProcessor.SUPPORTED_IMAGE_FORMATS else "document",
            "original_filename": original_name,
        }

    except HTTPException:
        raise
    except Exception as error:
        _log_failure("document_query_failed", error, request)
        raise HTTPException(500, "Document query failed")
    finally:
        # Limpiar archivo temporal
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)
        await file.close()


@app.post("/upload-document")
@limiter.limit(settings.ADMIN_RATE_LIMIT)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    _auth: bool = Depends(verify_admin_api_key),
):
    """Sube y procesa un documento legal (PDF, imagen, DOCX, etc.) con Docling."""
    from ingestion.docling_processor import LegalDocumentProcessor

    raw_path: Optional[Path] = None
    processed_path: Optional[Path] = None
    processed_created = False
    try:
        original_name = (
            (file.filename or "upload").replace("\\", "/").rsplit("/", 1)[-1]
        )
        original_name = "".join(char for char in original_name if char.isprintable())[
            :255
        ]

        # Verificar extensión del archivo
        file_ext = Path(original_name).suffix.lower()
        supported_exts = LegalDocumentProcessor.SUPPORTED_IMAGE_FORMATS | LegalDocumentProcessor.SUPPORTED_DOC_FORMATS
        if file_ext not in supported_exts:
            raise HTTPException(
                400,
                f"Formato no soportado: {file_ext}. "
                f"Formatos soportados: PDF, DOCX, PPTX, XLSX, imágenes (PNG, JPEG, TIFF, etc.)"
            )

        raw_directory = RAW_PDFS_DIR.resolve()
        raw_directory.mkdir(parents=True, exist_ok=True)
        server_name = f"{uuid.uuid4().hex}{file_ext}"
        raw_path = (raw_directory / server_name).resolve()
        if raw_path.parent != raw_directory:
            raise HTTPException(400, "Invalid upload path")

        total_size = 0
        with raw_path.open("xb") as buffer:
            while chunk := await file.read(1024 * 1024):
                total_size += len(chunk)
                if total_size > settings.MAX_FILE_SIZE:
                    raise HTTPException(413, "File exceeds maximum allowed size")
                buffer.write(chunk)

        if total_size == 0:
            raise HTTPException(400, "Empty file")

        document_processor = _get_document_processor(app)
        processed_content = await document_processor.process_document(
            str(raw_path), write_output=False
        )

        processed_directory = PROCESSED_DIR.resolve()
        processed_directory.mkdir(parents=True, exist_ok=True)
        processed_path = processed_directory / f"{raw_path.stem}.md"
        with processed_path.open("x", encoding="utf-8", newline="") as f:
            processed_created = True
            f.write(processed_content)

        # Determinar tipo de documento
        document_type = "image" if file_ext in LegalDocumentProcessor.SUPPORTED_IMAGE_FORMATS else "document"

        # Publish before RAG; upload cleanup below does not delete published evidence.
        evidence = persist_source_evidence(
            raw_path,
            processed_path,
            processed_content,
            PROCESSED_DIR.parent / "source_evidence",
        )

        await app.state.rag_engine.add_document(
            processed_content,
            {
                "filename": server_name,
                "original_filename": original_name,
                "title": original_name,
                "document_type": document_type,
                "source": "upload-document",
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
            "file_type": document_type,
            "evidence_id": evidence.evidence_id,
            "graph_write_state": "unverified",
            "message": f"{document_type.capitalize()} procesado correctamente con Docling",
        }
    except HTTPException:
        if raw_path:
            raw_path.unlink(missing_ok=True)
        if processed_created and processed_path:
            processed_path.unlink(missing_ok=True)
        raise
    except Exception as error:
        if raw_path:
            raw_path.unlink(missing_ok=True)
        if processed_created and processed_path:
            processed_path.unlink(missing_ok=True)
        _log_failure("document_upload_failed", error, request)
        raise HTTPException(500, "Document processing failed")
    finally:
        await file.close()


# Mantener el endpoint antiguo por compatibilidad
@app.post("/upload-pdf")
@limiter.limit(settings.ADMIN_RATE_LIMIT)
async def upload_pdf(
    request: Request,
    file: UploadFile = File(...),
    _auth: bool = Depends(verify_admin_api_key),
):
    """Sube y procesa un PDF legal con Docling (endpoint deprecado, usar /upload-document)."""
    return await upload_document(request, file, _auth)


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
async def legal_query(request: Request, payload: LegalQueryRequest, principal: Principal = Depends(require_principal)):
    try:
        cache_key, history = await _prepare_query_context(payload, principal.id, "query")
        return await answer_query(app.state, payload.query, payload.language, history=history,
                                  context=payload.context, cache_key=cache_key)
    except HTTPException:
        raise
    except DatabaseUnavailableError:
        raise HTTPException(503, "Chat persistence unavailable")
    except Exception as error:
        _log_failure("legal_query_failed", error, request)
        raise HTTPException(500, "Legal query failed")



@app.post("/legal-query-stream")
@limiter.limit(settings.LLM_RATE_LIMIT)
async def legal_query_stream(request: Request, payload: LegalQueryRequest, principal: Principal = Depends(require_principal)):
    """NDJSON v1: etapas en vivo y texto solo ya validado, nunca borradores.

    Autorización y conversación ajena (401/404) se resuelven antes de abrir el
    stream; los fallos posteriores salen como evento `error` con `code`.
    """
    try:
        cache_key, history = await _prepare_query_context(payload, principal.id, "query")
        if payload.conversation_id:
            from models.chat_models import MessageCreate, MessageRole
            await chat_service.add_message(payload.conversation_id, principal.id,
                MessageCreate(content=payload.query, role=MessageRole.USER, language=payload.language))
    except HTTPException:
        raise
    except DatabaseUnavailableError:
        raise HTTPException(503, "Chat persistence unavailable")
    except ValueError:
        raise HTTPException(404, "Conversation not found")
    except Exception as error:
        _log_failure("legal_query_stream_failed", error, request)
        raise HTTPException(500, "Legal query stream failed")

    async def persist(result):
        await _persist_assistant_response(payload.conversation_id, principal.id, result["response"],
                                         payload.language, {"sources": result["sources"], "validation": result["validation"]})

    request_id = getattr(request.state, "request_id", "unknown")
    source = stream_legal_query(
        run_pipeline=lambda on_stage: answer_query(app.state, payload.query, payload.language, history=history,
                                                   context=payload.context, cache_key=cache_key, on_stage=on_stage),
        extract_text=lambda result: _extract_response_text(result["response"], payload.language),
        persist=persist,
        request_id=request_id,
        language=payload.language,
        timeout_s=settings.STREAM_PIPELINE_TIMEOUT_SECONDS,
    )
    # StreamGuard garantiza esquema, un solo terminal + done, chunk == final y watchdog.
    events = guard_stream(
        source,
        extract_text=lambda data: _extract_response_text(data["response"], payload.language),
        request_id=request_id,
        idle_timeout_s=settings.STREAM_IDLE_TIMEOUT_SECONDS,
    )
    return StreamingResponse(events, media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})



MAX_TELEMETRY_BYTES = 4096


@app.post("/telemetry/stream", status_code=204)
@limiter.limit(settings.TELEMETRY_RATE_LIMIT)
async def stream_telemetry(request: Request):
    """Telemetría del cliente: solo números y el `request_id`, nunca texto.

    Acepta `text/plain` (navigator.sendBeacon evita así el preflight CORS); el cuerpo es JSON.
    """
    body = await request.body()
    if len(body) > MAX_TELEMETRY_BYTES:
        raise HTTPException(413, "Telemetry payload too large")
    try:
        item = StreamTelemetry.model_validate_json(body)
    except ValueError:
        raise HTTPException(422, "Invalid telemetry payload")
    stream_metrics.record(item)
    return Response(status_code=204)


@app.get("/telemetry/stream/summary")
@limiter.limit(settings.ADMIN_RATE_LIMIT)
async def stream_telemetry_summary(request: Request, _auth: bool = Depends(verify_admin_api_key)):
    """p50/p95 por etapa, resultados y líneas inválidas de los últimos streams (solo administración)."""
    return {"success": True, "summary": stream_metrics.summary()}


def _feedback_store() -> FeedbackStore:
    store = getattr(app.state, "feedback_store", None)
    if store is None:
        store = FeedbackStore(settings.FEEDBACK_DIR)
        app.state.feedback_store = store
    return store


async def _rated_exchange(conversation_id: str, owner_id: str):
    """Última consulta y respuesta de una conversación **propia**; ``(None, None)`` si no se pueden leer."""
    try:
        if not await chat_service.get_conversation(conversation_id, owner_id):
            return None, None
        messages = await chat_service.get_conversation_messages(conversation_id, owner_id, limit=12)
    except (DatabaseUnavailableError, ValueError):
        return None, None
    role = lambda m: getattr(m.role, "value", m.role)  # noqa: E731
    answer = next((m.content for m in reversed(messages) if role(m) == "assistant"), None)
    query = next((m.content for m in reversed(messages) if role(m) == "user"), None)
    return query, answer


@app.post("/feedback", status_code=201)
@limiter.limit(settings.FEEDBACK_RATE_LIMIT)
async def submit_feedback(request: Request, payload: FeedbackIn, principal: Principal = Depends(require_principal)):
    """👍/👎 con motivo. El texto solo se guarda con `share_text` y 👎 (cola de candidatos, pendiente de revisión)."""
    query = answer = None
    if payload.share_text and payload.rating == "down" and payload.conversation_id:
        query, answer = await _rated_exchange(payload.conversation_id, principal.id)
    record = _feedback_store().add(principal.id, payload, query=query, answer=answer)
    return {"success": True, "id": record["id"], "queued": record["queue_status"] == "pending"}


@app.get("/feedback/queue")
@limiter.limit(settings.QUALITY_RATE_LIMIT)
async def feedback_queue(request: Request, _admin: str = Depends(require_quality_admin)):
    store = _feedback_store()
    return {"success": True, "summary": store.summary(), "items": store.queue("pending")[:50]}


class QueueDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["accept", "reject"]


@app.post("/feedback/queue/{item_id}/decision")
@limiter.limit(settings.QUALITY_RATE_LIMIT)
async def decide_feedback(request: Request, item_id: str, payload: QueueDecision, _admin: str = Depends(require_quality_admin)):
    """Acepta o descarta un candidato. Aceptar NO lo agrega al gold: lo deja listo para que abogados lo redacten."""
    record = _feedback_store().decide(item_id, payload.decision)
    if record is None:
        raise HTTPException(404, "Queue item not found")
    return {"success": True, "id": record["id"], "queue_status": record["queue_status"]}


@app.get("/quality/published")
@limiter.limit(settings.QUALITY_RATE_LIMIT)
async def quality_published(request: Request):
    """Métricas publicadas (agregados, sin texto de consultas ni respuestas)."""
    return {"success": True, "published": load_published()}


@app.get("/quality/admin/overview")
@limiter.limit(settings.QUALITY_RATE_LIMIT)
async def quality_admin_overview(request: Request, _admin: str = Depends(require_quality_admin)):
    """Regresiones entre commits, colas de revisión, feedback y latencia del stream."""
    return {"success": True, "overview": admin_overview(_feedback_store(), stream_metrics)}


@app.post(
    "/generate-pdf-report",
    responses={
        500: {"description": "PDF generation failed"},
        503: {"description": "PDF generation unavailable"},
    },
)
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


class TTSRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., min_length=1, max_length=5000)
    language: SupportedLanguage = "spanish"


@app.post("/tts/synthesize")
@limiter.limit(settings.LLM_RATE_LIMIT)
async def synthesize_speech(
    request: Request,
    payload: TTSRequest,
    principal: Principal = Depends(require_principal),
):
    """
    Sintetiza texto a voz.
    - Para español: Retorna indicación de usar Web Speech API en el frontend
    - Para quechua: Usa MMS-TTS para generar audio WAV
    """
    try:
        language_code = "qu" if payload.language == "quechua" else "es"
        
        # Para español, usar Web Speech API en el frontend
        if language_code == "es":
            return {
                "success": True,
                "method": "web_speech_api",
                "language": "es",
                "message": "Use Web Speech API in the browser for Spanish",
                "text": payload.text,
            }
        
        # Para quechua, usar MMS-TTS
        tts_service = TTSService()
        
        if not tts_service.is_available(language_code):
            raise HTTPException(
                503, 
                f"TTS not available for language: {payload.language}"
            )
        
        audio_bytes = await tts_service.synthesize_quechua(payload.text)
        
        if audio_bytes is None:
            raise HTTPException(500, "Failed to synthesize audio")
        
        return Response(
            content=audio_bytes,
            media_type="audio/wav",
            headers={
                "Content-Disposition": 'attachment; filename="quechua_audio.wav"',
                "Cache-Control": "no-store",
            },
        )
        
    except HTTPException:
        raise
    except Exception as error:
        _log_failure("tts_synthesis_failed", error, request)
        raise HTTPException(500, "TTS synthesis failed")


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
