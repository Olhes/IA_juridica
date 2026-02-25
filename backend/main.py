from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
import uvicorn
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional
import asyncio
from dotenv import load_dotenv
import traceback

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Rate limiting
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded

    SLOWAPI_AVAILABLE = True
except ImportError:
    SLOWAPI_AVAILABLE = False

# Módulos del sistema
from config.settings import settings
from ingestion.pipeline import LegalIngestionPipeline
from rag.lightrag_engine import LegalRAGEngine
from agents.pydantic_agents import LegalAgent
from context.context_engineering import ContextEngineer

# ── Módulos de validación y optimización ──────────────────────────────
from validation.response_validator import ResponseValidator, ValidationConfig
from optimization.llm_optimizer import LLMOptimizer
# ─────────────────────────────────────────────────────────────────────────────


DOCS_DIR = BASE_DIR / "docs"
RAW_PDFS_DIR = DOCS_DIR / "raw_pdfs"
PROCESSED_DIR = DOCS_DIR / "processed"
KNOWLEDGE_GRAPH_DIR = DOCS_DIR / "knowledge_graph"

# Rate limiter
if SLOWAPI_AVAILABLE and settings.RATE_LIMIT_ENABLED:
    limiter = Limiter(key_func=get_remote_address)
else:
    limiter = None

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


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


async def verify_admin_api_key(api_key: Optional[str] = Security(api_key_header)):
    if settings.is_development():
        return True
    if not api_key or api_key != settings.SECRET_KEY:
        raise HTTPException(status_code=403, detail="API key inválida")
    return True


# ── Modelos de request/response ────────────────────────────────────────────────


class LegalQueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    language: str = Field(default="spanish")
    context: Optional[Dict[str, Any]] = None


class PDFReportRequest(BaseModel):
    query: str = Field(..., min_length=1)
    response: Dict[str, Any]


# ── Lifespan ───────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Inicializando IA Jurídica v2.1...")

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


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="IA Jurídica - Sistema Legal Bilingüe",
    description="Asistente legal especializado con RAG avanzado y validación anti-alucinación",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

if limiter is not None:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)


# ── Endpoints ──────────────────────────────────────────────────────────────────


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
    # ──────────────────────────────────────────────────────────────────────────

    critical_ok = all(
        components.get(c) in ("ready", "fallback")
        for c in ("cohere", "lightrag", "pydantic_ai")
    )

    return {
        "status": "healthy" if critical_ok else "degraded",
        "components": components,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.post("/upload-pdf")
async def upload_pdf(
    file: UploadFile = File(...), _auth: bool = Depends(verify_admin_api_key)
):
    """Sube y procesa un PDF legal con Docling."""
    try:
        filename = file.filename or ""
        if not filename.endswith(".pdf"):
            raise HTTPException(400, "Solo se permiten archivos PDF")

        file_path = RAW_PDFS_DIR / filename
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())

        pdf_processor = _get_pdf_processor(app)
        processed_content = await pdf_processor.process_pdf(str(file_path))

        processed_path = PROCESSED_DIR / f"{filename}.md"
        with open(processed_path, "w", encoding="utf-8") as f:
            f.write(processed_content)

        await app.state.rag_engine.add_document(
            processed_content,
            {
                "filename": filename,
                "title": filename,
                "document_type": "legal_pdf",
                "source": "upload-pdf",
            },
            filename,
        )

        # Actualizar el CrossChecker con el nuevo documento [NUEVO]
        if hasattr(app.state, "response_validator"):
            app.state.response_validator.cross_checker.update_documents(
                app.state.rag_engine.documents
            )

        return {
            "success": True,
            "filename": filename,
            "processed_path": str(processed_path),
            "message": "PDF procesado correctamente con Docling",
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Error procesando PDF: {repr(e)}")


@app.post("/batch-process")
async def batch_process_pdfs(_auth: bool = Depends(verify_admin_api_key)):
    """Procesa todos los PDFs del directorio raw_pdfs."""
    try:
        results = await app.state.ingestion_pipeline.process_all_pdfs()
        return {
            "success": True,
            "processed": results["processed_count"],
            "failed": results["failed_count"],
            "details": results["details"],
        }
    except Exception as e:
        raise HTTPException(500, f"Batch processing failed: {str(e)}")


@app.post("/legal-query")
async def legal_query(request: Request, payload: LegalQueryRequest):
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
            return {
                "success": True,
                "query": query,
                "language": language,
                "cached": True,
                **cached_result,
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

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Legal query failed: {str(e)}")


@app.post("/legal-query-stream")
async def legal_query_stream(payload: LegalQueryRequest):
    """Stream de respuesta legal directamente desde Cohere."""
    try:
        query = payload.query.strip()
        language = payload.language

        async def stream_generator():
            context = await app.state.rag_engine.query(query)
            async for chunk in app.state.legal_agent.stream_general_text(
                query, context, language
            ):
                if chunk:
                    for start in range(0, len(chunk), 24):
                        yield chunk[start : start + 24]
                        await asyncio.sleep(0)

        return StreamingResponse(
            stream_generator(),
            media_type="text/plain; charset=utf-8",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Legal query stream failed: {str(e)}")


@app.post("/generate-pdf-report")
async def generate_pdf_report(payload: PDFReportRequest):
    """Genera reporte PDF legal con ReportLab."""
    try:
        from utils.pdf_generator import generate_legal_pdf

        pdf_path = generate_legal_pdf(
            query=payload.query,
            response_data=payload.response,
            output_dir=settings.PDF_OUTPUT_DIR,
        )
        return FileResponse(
            path=pdf_path,
            media_type="application/pdf",
            filename=Path(pdf_path).name,
        )
    except ImportError:
        return {
            "success": False,
            "message": "reportlab no instalado. Ejecuta: pip install reportlab",
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"PDF generation failed: {str(e)}")


@app.get("/knowledge-graph")
async def get_knowledge_graph():
    try:
        graph_data = await app.state.rag_engine.get_knowledge_graph()
        return {"success": True, "graph": graph_data}
    except Exception as e:
        raise HTTPException(500, f"Failed to get knowledge graph: {str(e)}")


@app.post("/evaluate-system")
async def evaluate_system(_auth: bool = Depends(verify_admin_api_key)):
    try:
        evaluation_suite = _get_evaluation_suite(app)
        if evaluation_suite is None:
            raise HTTPException(503, "Evaluación deshabilitada por configuración")
        evaluation_results = await evaluation_suite.run_full_evaluation()
        return {"success": True, "results": evaluation_results}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Evaluation failed: {str(e)}")


@app.get("/documents")
async def list_documents():
    try:
        docs = await app.state.rag_engine.list_documents()
        return {"success": True, "documents": docs}
    except Exception as e:
        raise HTTPException(500, f"Failed to list documents: {str(e)}")


# ── Endpoint de estadísticas de validación ────────────────────────────

@app.get("/validation-stats")
async def get_validation_stats():
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
    except Exception as e:
        raise HTTPException(500, f"Stats failed: {str(e)}")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
