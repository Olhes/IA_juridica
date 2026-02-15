#!/usr/bin/env python
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

# Import our modules
from config.settings import settings
from ingestion.docling_processor import LegalPDFProcessor
from ingestion.pipeline import LegalIngestionPipeline
from rag.lightrag_engine import LegalRAGEngine
from agents.pydantic_agents import LegalAgent
from evaluation.deepeval_tests import LegalEvaluationSuite
from context.context_engineering import ContextEngineer


DOCS_DIR = BASE_DIR / "docs"
RAW_PDFS_DIR = DOCS_DIR / "raw_pdfs"
PROCESSED_DIR = DOCS_DIR / "processed"
KNOWLEDGE_GRAPH_DIR = DOCS_DIR / "knowledge_graph"

# Rate limiter setup
if SLOWAPI_AVAILABLE and settings.RATE_LIMIT_ENABLED:
    limiter = Limiter(key_func=get_remote_address)
else:
    limiter = None

# API Key auth para endpoints administrativos
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_admin_api_key(api_key: Optional[str] = Security(api_key_header)):
    """Verifica API key para endpoints administrativos"""
    if settings.is_development():
        return True  # Sin auth en desarrollo
    if not api_key or api_key != settings.SECRET_KEY:
        raise HTTPException(status_code=403, detail="API key inválida")
    return True


class LegalQueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    language: str = Field(default="spanish")
    context: Optional[Dict[str, Any]] = None


class PDFReportRequest(BaseModel):
    query: str = Field(..., min_length=1)
    response: Dict[str, Any]

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Inicializando IA Jurídica...")

    if not hasattr(app.state, "rag_engine"):
        # Crear carpetas UNA sola vez
        RAW_PDFS_DIR.mkdir(parents=True, exist_ok=True)
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        KNOWLEDGE_GRAPH_DIR.mkdir(parents=True, exist_ok=True)

        # Inicializar componentes UNA sola vez
        app.state.pdf_processor = LegalPDFProcessor()
        app.state.ingestion_pipeline = LegalIngestionPipeline()
        app.state.rag_engine = LegalRAGEngine()
        
        # ⚠️ CRÍTICO: Inicializar storages de LightRAG (async)
        # Sin esto, obtendrás StorageNotInitializedError
        await app.state.rag_engine.initialize_storages()
        
        app.state.legal_agent = LegalAgent()
        app.state.evaluation_suite = LegalEvaluationSuite()
        app.state.context_engineer = ContextEngineer()

        print("Componentes inicializados")
    else:
        print("Componentes ya inicializados, saltando...")

    yield

    print("Cerrando IA Jurídica...")


app = FastAPI(
    title="IA Jurídica - Sistema Legal Bilingüe",
    description="Asistente legal especializado con RAG avanzado",
    version=settings.APP_VERSION,
    lifespan=lifespan
)

# Rate limiting
if limiter is not None:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware - usar configuración centralizada
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)


@app.get("/")
async def root():
    return {"message": "IA Jurídica API v2.0 - Sistema Legal con Docling y RAG"}

@app.get("/health")
async def health_check():
    """Health check real que verifica el estado de cada componente"""
    components = {}
    
    # Verificar Cohere API key
    components["cohere"] = "ready" if settings.COHERE_API_KEY else "not_configured"
    
    # Verificar RAG engine
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
    
    # Verificar agente legal
    try:
        agent = getattr(app.state, "legal_agent", None)
        if agent:
            from agents.pydantic_agents import PYDANTIC_AI_AVAILABLE
            components["pydantic_ai"] = "ready" if PYDANTIC_AI_AVAILABLE else "fallback"
        else:
            components["pydantic_ai"] = "unavailable"
    except Exception:
        components["pydantic_ai"] = "error"
    
    # Verificar context engineer
    components["context_engineer"] = "ready" if getattr(app.state, "context_engineer", None) else "unavailable"
    
    # Estado general: healthy si los componentes críticos están listos
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
async def upload_pdf(file: UploadFile = File(...), _auth: bool = Depends(verify_admin_api_key)):
    """Upload and process legal PDF with Docling (requiere API key en producción)"""
    try:
        filename = file.filename or ""

        # Validate file type
        if not filename.endswith('.pdf'):
            raise HTTPException(400, "Only PDF files are allowed")
        
        # Save uploaded file
        file_path = RAW_PDFS_DIR / filename
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Process PDF with Docling (AHORA CON AWAIT)
        processed_content = await app.state.pdf_processor.process_pdf(str(file_path))

        # Save processed content
        processed_path = PROCESSED_DIR / f"{filename}.md"
        with open(processed_path, "w", encoding="utf-8") as f:
            f.write(processed_content)
        
        metadata = {
            "filename": filename,
            "title": filename,
            "document_type": "legal_pdf",
            "source": "upload-pdf"
        }

        # Add to RAG engine
        await app.state.rag_engine.add_document(
            processed_content,
            metadata,
            filename
        )
        
        return {
            "success": True,
            "filename": filename,
            "processed_path": str(processed_path),
            "message": "PDF processed successfully with Docling"
        }
        
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Error processing PDF: {repr(e)}")


@app.post("/batch-process")
async def batch_process_pdfs(_auth: bool = Depends(verify_admin_api_key)):
    """Process all PDFs in raw_pdfs directory (requiere API key en producción)"""
    try:
        results = await app.state.ingestion_pipeline.process_all_pdfs()

        return {
            "success": True,
            "processed": results["processed_count"],
            "failed": results["failed_count"],
            "details": results["details"]
        }
    except Exception as e:
        raise HTTPException(500, f"Batch processing failed: {str(e)}")

@app.post("/legal-query")
async def legal_query(request: Request, payload: LegalQueryRequest):
    """Process legal query with RAG + Cohere Rerank + Context Engineering + Pydantic AI"""
    try:
        query = payload.query.strip()
        language = payload.language

        # 1. Búsqueda con reranking (Cohere rerank-multilingual-v3.0)
        rag_result = await app.state.rag_engine.query_with_rerank(query)
        
        # 2. Construir prompt enriquecido con ContextEngineer
        documents = rag_result.get("documents", [])
        enriched_prompt, enriched_context = app.state.context_engineer.build_legal_prompt(
            query=query,
            documents=documents,
            language=language,
        )
        
        # 3. Generar respuesta con Pydantic AI agent + prompt enriquecido
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
        
        return {
            "success": True,
            "query": query,
            "language": language,
            "response": response_payload,
            "sources": rag_result.get("sources", []),
            "metadata": {
                "rerank_scores": rag_result.get("rerank_scores", []),
                "retrieval_method": rag_result.get("method", "unknown"),
                "total_candidates": rag_result.get("total_candidates", 0),
                "enriched_context": {
                    "location": enriched_context.get("detected_location"),
                    "legal_topic": enriched_context.get("legal_topic"),
                    "urgency": enriched_context.get("urgency_level"),
                },
            },
        }
        
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Legal query failed: {str(e)}")

@app.post("/legal-query-stream")
async def legal_query_stream(payload: LegalQueryRequest):
    """Stream legal response text directly from backend model."""
    try:
        query = payload.query.strip()
        language = payload.language

        async def stream_generator():
            context = await app.state.rag_engine.query(query)
            async for chunk in app.state.legal_agent.stream_general_text(query, context, language):
                if chunk:
                    for start in range(0, len(chunk), 24):
                        yield chunk[start:start + 24]
                        await asyncio.sleep(0)

        return StreamingResponse(
            stream_generator(),
            media_type="text/plain; charset=utf-8",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no"
            }
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Legal query stream failed: {str(e)}")

@app.post("/generate-pdf-report")
async def generate_pdf_report(payload: PDFReportRequest):
    """Generate legal PDF report with ReportLab"""
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
        # Fallback si reportlab no está instalado
        return {
            "success": False,
            "message": "reportlab no instalado. Ejecuta: pip install reportlab",
            "query": payload.query,
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"PDF generation failed: {str(e)}")

@app.get("/knowledge-graph")
async def get_knowledge_graph():
    """Get knowledge graph visualization data"""
    try:
        graph_data = await app.state.rag_engine.get_knowledge_graph()

        return {
            "success": True,
            "graph": graph_data
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to get knowledge graph: {str(e)}")

@app.post("/evaluate-system")
async def evaluate_system(_auth: bool = Depends(verify_admin_api_key)):
    """Run system evaluation with DeepEval (requiere API key en producción)"""
    try:
        evaluation_results = await app.state.evaluation_suite.run_full_evaluation()

        return {
            "success": True,
            "results": evaluation_results
        }
    except Exception as e:
        raise HTTPException(500, f"Evaluation failed: {str(e)}")

@app.get("/documents")
async def list_documents():
    """List all processed documents"""
    try:
        docs = await app.state.rag_engine.list_documents()

        return {
            "success": True,
            "documents": docs
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to list documents: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
