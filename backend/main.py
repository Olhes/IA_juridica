"""FastAPI application entrypoint, lifespan wiring, middleware, and system routes."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Optional
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import uvicorn

from utils.console import configure_console_output

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
configure_console_output()
load_dotenv(BASE_DIR / ".env")

from agents.pydantic_agents import LegalAgent
from config.settings import settings
from context.context_engineering import ContextEngineer
from database.errors import DatabaseUnavailableError
from database.redis_adapter import redis_adapter
from database.surreal_connection import close_all_surreal
from ingestion.pipeline import LegalIngestionPipeline
from ingestion.sat_graph.postgres import PostgresSATGraphStore
from ingestion.sat_graph.runtime import runtime_sat_store
from ingestion.sat_graph.store import stage_document
from modules.auth.routes.auth_routes import router as auth_router
from modules.chat.routes.chat_routes import router as chat_router
from modules.chat.services.chat_service import chat_service
from modules.validation.services.response_validator import (
    ResponseValidator,
    ValidationConfig,
)
from optimization.llm_optimizer import LLMOptimizer
from retrieval.sat_chat import SATChatRetriever
from routers.documents import router as documents_router
from routers.quality import router as quality_router
from routers.queries import (
    LegalQueryRequest,
    _extract_response_text,
    _ndjson_event,
    _prepare_query_context,
    legal_query,
    legal_query_stream,
    router as queries_router,
)
from routers.sat_admin import router as sat_admin_router
from security import (
    client_ip_key,
    issue_session,
    limiter,
    principal_from_request,
    set_session_cookie,
)
from services.quality_reports import admin_overview, load_published
from services.sat_api import router as sat_api_router
from services.sat_corpus_routes import router as sat_corpus_router

DOCS_DIR = PROJECT_ROOT / "docs"
RAW_PDFS_DIR = DOCS_DIR / "raw_pdfs"
PROCESSED_DIR = DOCS_DIR / "processed"
KNOWLEDGE_GRAPH_DIR = DOCS_DIR / "knowledge_graph"

logger = logging.getLogger("ia_juridica.api")


def sat_graph_store():
    return runtime_sat_store()


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


def _get_document_processor(app_instance: FastAPI):
    processor = getattr(app_instance.state, "document_processor", None)
    if processor is None:
        from ingestion.docling_processor import LegalDocumentProcessor

        processor = LegalDocumentProcessor()
        app_instance.state.document_processor = processor
    return processor


def _get_pdf_processor(app_instance: FastAPI):
    processor = getattr(app_instance.state, "pdf_processor", None)
    return processor if processor is not None else _get_document_processor(app_instance)


async def _evaluate_harness(provider="application", limit=None):
    """Ejecuta el harness offline sin sobrescribir informes de evaluaciones reales."""
    import tempfile
    from evaluation.harness.runner import DEFAULT_CASSETTE, NVIDIA_CASSETTE, run_legal_qa

    cassette = NVIDIA_CASSETTE if provider == "nvidia-voyage" else DEFAULT_CASSETTE
    if not cassette.is_file():
        raise FileNotFoundError("Cassette de evaluación no disponible")

    with tempfile.TemporaryDirectory(prefix="legal-qa-eval-") as directory:
        kwargs = {
            "judge_name": "none",
            "real": False,
            "samples": 1,
            "results_dir": directory,
        }
        if provider == "nvidia-voyage":
            kwargs.update(provider=provider, limit=limit, cassette_path=cassette)
        _, report = await run_legal_qa(**kwargs)
    return report


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    logger.info("Starting IA Jurídica %s", settings.APP_VERSION)

    configuration = settings.validate_configuration()
    if not configuration["valid"]:
        raise RuntimeError(
            "Invalid configuration: " + "; ".join(configuration["issues"])
        )

    try:
        await chat_service.initialize()
        logger.info("Chat service initialized")
    except Exception as error:
        logger.warning(
            "chat_service_init_failed error_type=%s; continuing without persistent chat",
            type(error).__name__,
        )

    if not hasattr(app_instance.state, "rag_engine"):
        RAW_PDFS_DIR.mkdir(parents=True, exist_ok=True)
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        KNOWLEDGE_GRAPH_DIR.mkdir(parents=True, exist_ok=True)

        sat_mode = settings.RAG_ENGINE.lower() == "sat"
        app_instance.state.rag_engine = None
        if not sat_mode:
            from modules.rag.services.lightrag_engine import LegalRAGEngine

            app_instance.state.rag_engine = LegalRAGEngine(
                working_dir=str(KNOWLEDGE_GRAPH_DIR)
            )
        if sat_mode:
            store = await asyncio.to_thread(sat_graph_store)
            if isinstance(store, PostgresSATGraphStore):
                if not await asyncio.to_thread(store.is_ready):
                    try:
                        await asyncio.to_thread(store.ensure_schema)
                    except Exception as error:
                        logger.warning(
                            "sat_schema_unavailable error_type=%s",
                            type(error).__name__,
                        )
                    else:
                        logger.warning(
                            "sat_corpus_empty: publica el primer documento en /sat-graph/review"
                        )
            app_instance.state.query_retriever = SATChatRetriever(
                store, settings.SAT_AS_OF
            )
        else:
            app_instance.state.query_retriever = app_instance.state.rag_engine

        app_instance.state.ingestion_pipeline = LegalIngestionPipeline(
            rag_engine=app_instance.state.rag_engine,
            legacy_rag_write=not sat_mode and settings.SAT_INGESTION_LEGACY_RAG,
            sat_store_factory=sat_graph_store,
        )
        app_instance.state.legal_agent = LegalAgent()
        app_instance.state.context_engineer = ContextEngineer()

        validation_config = ValidationConfig(
            hallucination_threshold=settings.EVALUATION_THRESHOLD,
            cross_check_threshold=0.55,
            min_confidence_score=0.30,
            max_self_correction_retries=2,
            enable_cross_check=True,
            enable_self_correction=True,
            enable_cultural_validation=True,
        )
        app_instance.state.response_validator = ResponseValidator(
            rag_engine=app_instance.state.query_retriever,
            cohere_client=app_instance.state.legal_agent.cohere_client,
            context_engineer=app_instance.state.context_engineer,
            config=validation_config,
        )
        app_instance.state.llm_optimizer = LLMOptimizer(
            cache_ttl_seconds=settings.CACHE_TTL,
            max_cache_size=settings.CACHE_MAX_SIZE,
        )
        logger.info("Core components initialized")

    if settings.RAG_ENGINE.lower() == "sat":
        retriever = app_instance.state.query_retriever
        app_instance.state.corpus_state = (
            "ready" if await asyncio.to_thread(retriever.corpus_ready) else "degraded"
        )
        app_instance.state.corpus_task = asyncio.create_task(asyncio.sleep(0))
    else:
        app_instance.state.corpus_state = "loading"
        app_instance.state.corpus_task = asyncio.create_task(
            load_heavy_components(app_instance.state.rag_engine, PROCESSED_DIR)
        )
    try:
        yield
    finally:
        task = app_instance.state.corpus_task
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        app_instance.state.corpus_state = "stopped"
        finalizer = getattr(
            getattr(app_instance.state.rag_engine, "rag", None),
            "finalize_storages",
            None,
        )
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
        await asyncio.to_thread(close_all_surreal)


async def load_heavy_components(rag_engine, processed_dir):
    """Load corpus once; retry bounded storage failures; never re-ingest on startup."""
    for attempt in range(3):
        try:
            await asyncio.wait_for(rag_engine.initialize_storages(), timeout=60)
            await asyncio.wait_for(
                rag_engine.load_processed_documents(str(processed_dir)), timeout=120
            )
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

app.include_router(chat_router)
app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(queries_router)
app.include_router(quality_router)
app.include_router(sat_admin_router)
if settings.RAG_ENGINE.lower() == "sat":
    app.include_router(sat_corpus_router)
    app.include_router(sat_api_router)


@app.exception_handler(DatabaseUnavailableError)
async def database_unavailable_handler(
    request: Request, error: DatabaseUnavailableError
):
    _log_failure("chat_persistence_unavailable", error, request)
    return JSONResponse(
        status_code=503, content={"detail": "Chat persistence unavailable"}
    )


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
    except Exception as error:
        _log_failure("session_bootstrap_failed", error, request)
        raise HTTPException(status_code=500, detail="Failed to create session")


@app.get("/")
async def root():
    return {
        "message": f"IA Jurídica API {settings.APP_VERSION} - Sistema Legal con Docling, RAG y Validación Anti-Alucinación"
    }


@app.get("/ready")
async def readiness():
    phase = getattr(app.state, "corpus_state", "unavailable")
    if phase == "degraded":
        probe = getattr(
            getattr(app.state, "query_retriever", None), "corpus_ready", None
        )
        if callable(probe) and await asyncio.to_thread(probe):
            app.state.corpus_state = phase = "ready"
    if phase != "ready":
        raise HTTPException(503, "Legal corpus unavailable")
    return {"status": "ready", "rag_engine": settings.RAG_ENGINE.lower()}


@app.get("/health")
async def health_check():
    """Health check que incluye estado del pipeline de validación."""
    components = {
        "corpus": getattr(app.state, "corpus_state", "unavailable"),
        "cohere": "ready" if settings.COHERE_API_KEY else "not_configured",
    }

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

    if settings.RAG_ENGINE.lower() == "sat":
        components["sat"] = (
            "ready" if getattr(app.state, "query_retriever", None) else "unavailable"
        )

    try:
        agent = getattr(app.state, "legal_agent", None)
        components["pydantic_ai"] = "fallback" if agent else "unavailable"
    except Exception:
        components["pydantic_ai"] = "error"

    components["context_engineer"] = (
        "ready" if getattr(app.state, "context_engineer", None) else "unavailable"
    )
    components["response_validator"] = (
        "ready" if getattr(app.state, "response_validator", None) else "unavailable"
    )
    components["llm_optimizer"] = (
        "ready" if getattr(app.state, "llm_optimizer", None) else "unavailable"
    )

    try:
        redis_health = await redis_adapter.health_check()
        components["redis"] = redis_health.get("status", "unknown")
    except Exception:
        components["redis"] = "error"

    try:
        db_health = await chat_service.db.health_check()
        components["postgresql"] = db_health.get("status", "unknown")
    except Exception:
        components["postgresql"] = "error"

    primary_engine = "sat" if settings.RAG_ENGINE.lower() == "sat" else "lightrag"
    critical_ok = (
        all(
            components.get(name) in ("ready", "fallback")
            for name in ("cohere", primary_engine, "pydantic_ai")
        )
        and components.get("postgresql") == "healthy"
        and components.get("corpus") == "ready"
    )

    return {
        "status": "healthy" if critical_ok else "degraded",
        "components": components,
        "rag_engine": settings.RAG_ENGINE.lower(),
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.is_development(),
        log_level="info",
    )
