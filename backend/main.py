#!/usr/bin/env python
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import os
from pathlib import Path
from contextlib import asynccontextmanager

import traceback


# Import our modules
from ingestion.docling_processor import LegalPDFProcessor
from ingestion.pipeline import LegalIngestionPipeline
from rag.lightrag_engine import LegalRAGEngine
from agents.pydantic_agents import LegalAgent
from evaluation.deepeval_tests import LegalEvaluationSuite

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Inicializando IA Jurídica...")

    if not hasattr(app.state, "rag_engine"):
        # Crear carpetas UNA sola vez
        os.makedirs("docs/raw_pdfs", exist_ok=True)
        os.makedirs("docs/processed", exist_ok=True)
        os.makedirs("docs/knowledge_graph", exist_ok=True)

        # Inicializar componentes UNA sola vez
        app.state.pdf_processor = LegalPDFProcessor()
        app.state.ingestion_pipeline = LegalIngestionPipeline()
        app.state.rag_engine = LegalRAGEngine()
        
        # ⚠️ CRÍTICO: Inicializar storages de LightRAG (async)
        # Sin esto, obtendrás StorageNotInitializedError
        await app.state.rag_engine.initialize_storages()
        
        app.state.legal_agent = LegalAgent()
        app.state.evaluation_suite = LegalEvaluationSuite()

        print("✅ Componentes inicializados")
    else:
        print("⚠️ Componentes ya inicializados, saltando...")

    yield

    print("🛑 Cerrando IA Jurídica...")


app = FastAPI(
    title="IA Jurídica - Sistema Legal Bilingüe",
    description="Asistente legal especializado con RAG avanzado",
    version="2.0.0",
    lifespan=lifespan
)


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"message": "IA Jurídica API v2.0 - Sistema Legal con Docling y RAG"}

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "components": {
            "docling": "ready",
            "lightrag": "ready",
            "pydantic_ai": "ready",
            "evaluation": "ready"
        }
    }

@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    """Upload and process legal PDF with Docling"""
    try:
        # Validate file type
        if not file.filename.endswith('.pdf'):
            raise HTTPException(400, "Only PDF files are allowed")
        
        # Save uploaded file
        file_path = Path("docs/raw_pdfs") / file.filename
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Process PDF with Docling (AHORA CON AWAIT)
        processed_content = await app.state.pdf_processor.process_pdf(str(file_path))

        # Save processed content
        processed_path = Path("docs/processed") / f"{file.filename}.md"
        with open(processed_path, "w", encoding="utf-8") as f:
            f.write(processed_content)
        
        metadata = {
            "filename": file.filename,
            "title": file.filename,
            "document_type": "legal_pdf",
            "source": "upload-pdf"
        }

        # Add to RAG engine
        await app.state.rag_engine.add_document(
            processed_content,
            metadata,
            file.filename
        )
        
        return {
            "success": True,
            "filename": file.filename,
            "processed_path": str(processed_path),
            "message": "PDF processed successfully with Docling"
        }
        
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Error processing PDF: {repr(e)}")


@app.post("/batch-process")
async def batch_process_pdfs():
    """Process all PDFs in raw_pdfs directory"""
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
async def legal_query(query: str, language: str = "spanish"):
    """Process legal query with RAG and Pydantic AI"""
    try:
        # Get relevant context from RAG
        context = await app.state.rag_engine.query(query)
        
        # Generate response with Pydantic AI usando respond_general
        response = await app.state.legal_agent.respond_general(query, context, language)
        
        return {
            "success": True,
            "query": query,
            "language": language,
            "response": response.dict() if hasattr(response, 'dict') else response,
            "sources": context.get("sources", [])
        }
        
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Legal query failed: {str(e)}")

@app.post("/generate-pdf-report")
async def generate_pdf_report(query: str, response: dict):
    """Generate legal PDF report"""
    try:
        # This would integrate with your PDF generation service
        return {
            "success": True,
            "message": "PDF report generation not implemented yet",
            "query": query,
            "response": response
        }
    except Exception as e:
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
async def evaluate_system():
    """Run system evaluation with DeepEval"""
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