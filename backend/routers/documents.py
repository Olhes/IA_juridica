"""Document query, upload, batch ingestion, and listing endpoints."""

import asyncio
import logging
from pathlib import Path
import shutil
from typing import Callable, Optional
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from config.settings import settings
from ingestion.conversion import convert_for_ingestion
from ingestion.source_evidence import persist_source_evidence
from models.request_types import SupportedLanguage
from security import Principal, limiter, require_principal, verify_admin_api_key

router = APIRouter(tags=["documents"])
logger = logging.getLogger("ia_juridica.api")


def _sanitize_upload_filename(raw_name: Optional[str]) -> str:
    name = (raw_name or "upload").replace("\\", "/").rsplit("/", 1)[-1]
    return "".join(char for char in name if char.isprintable())[:255]


async def save_validated_upload(
    file: UploadFile,
    dest_dir: Path,
    *,
    supported_exts: set[str],
    require_pdf_checks: bool = False,
    id_factory: Callable[[], object] = uuid.uuid4,
) -> tuple[str, str, str, Path]:
    """Validate upload metadata/bytes and stream into a confined server path."""
    original_name = _sanitize_upload_filename(file.filename)
    file_ext = Path(original_name).suffix.lower()
    if file_ext not in supported_exts:
        raise HTTPException(
            400,
            f"Formato no soportado: {file_ext}. "
            "Formatos soportados: PDF, DOCX, PPTX, XLSX, imágenes (PNG, JPEG, TIFF, etc.)",
        )
    if require_pdf_checks and file_ext == ".pdf" and file.content_type != "application/pdf":
        raise HTTPException(400, "Invalid PDF media type")

    resolved_dir = dest_dir.resolve()
    resolved_dir.mkdir(parents=True, exist_ok=True)
    server_name = f"{id_factory().hex}{file_ext}"
    target_path = (resolved_dir / server_name).resolve()
    if target_path.parent != resolved_dir:
        raise HTTPException(400, "Invalid upload path")

    total_size = 0
    first_chunk = True
    try:
        with target_path.open("xb") as buffer:
            while chunk := await file.read(1024 * 1024):
                if (
                    first_chunk
                    and require_pdf_checks
                    and file_ext == ".pdf"
                    and not chunk.startswith(b"%PDF-")
                ):
                    raise HTTPException(400, "Invalid PDF signature")
                first_chunk = False
                total_size += len(chunk)
                if total_size > settings.MAX_FILE_SIZE:
                    raise HTTPException(413, "File exceeds maximum allowed size")
                buffer.write(chunk)
    except Exception:
        target_path.unlink(missing_ok=True)
        raise

    if total_size == 0:
        target_path.unlink(missing_ok=True)
        raise HTTPException(400, "Empty file")

    return original_name, file_ext, server_name, target_path


def _cleanup_paths(*paths: Optional[Path]) -> None:
    for path in paths:
        if path:
            path.unlink(missing_ok=True)


def _count_tokens(text: str) -> int:
    import tiktoken

    try:
        encoding = tiktoken.encoding_for_model("command-r-plus-08-2024")
    except Exception:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


def _document_system_prompt(language: str, *, large_document: bool) -> str:
    from context.prompt_templates import get_legal_system_prompt

    if large_document:
        return (
            f"{get_legal_system_prompt()}\n\n"
            "INSTRUCCIONES ESPECÍFICAS PARA ANÁLISIS DE DOCUMENTOS GRANDES:\n"
            "1. El documento proporcionado es muy grande, por lo que se recuperaron fragmentos relevantes usando búsqueda semántica\n"
            "2. Basa tu respuesta SOLO en los fragmentos recuperados proporcionados\n"
            "3. Si la información necesaria no está en los fragmentos, indica explícitamente que no está disponible\n"
            "4. Cita la fuente específica cuando sea posible\n"
            "5. Organiza la respuesta en secciones claras con encabezados\n"
            "6. Mantén el tono profesional y técnico pero accesible\n\n"
            f"Responde en {language}."
        )
    return (
        f"{get_legal_system_prompt()}\n\n"
        "INSTRUCCIONES ESPECÍFICAS PARA ANÁLISIS DE DOCUMENTOS:\n"
        "1. Analiza el documento proporcionado en formato Markdown\n"
        "2. Identifica el tipo de documento (ley, reglamento, jurisprudencia, etc.)\n"
        "3. Extrae y estructura la información relevante: artículos modificados, cambios principales, plazos, entidades involucradas\n"
        "4. Cita artículos específicos y números de ley cuando sea posible\n"
        "5. Organiza la respuesta en secciones claras con encabezados\n"
        "6. Si el documento es una modificación legislativa, explica claramente qué cambia y qué no\n"
        "7. Mantén el tono profesional y técnico pero accesible\n\n"
        f"Responde en {language}."
    )


@router.post("/query-document")
@limiter.limit(settings.LLM_RATE_LIMIT)
async def query_document(
    request: Request,
    file: UploadFile = File(...),
    query: str = Form(...),
    language: SupportedLanguage = Form("spanish"),
    principal: Principal = Depends(require_principal),
):
    """Procesa un documento temporalmente (imagen/PDF) y responde preguntas usando Cohere."""
    import main as runtime
    from agents.pydantic_agents import LegalAgent
    from ingestion.docling_processor import LegalDocumentProcessor

    temp_path: Optional[Path] = None
    try:
        supported_exts = (
            LegalDocumentProcessor.SUPPORTED_IMAGE_FORMATS
            | LegalDocumentProcessor.SUPPORTED_DOC_FORMATS
        )
        temp_dir = runtime.BASE_DIR / "temp"
        original_name, file_ext, _, temp_path = await save_validated_upload(
            file,
            temp_dir,
            supported_exts=supported_exts,
            id_factory=runtime.uuid.uuid4,
        )

        document_processor = runtime._get_document_processor(runtime.app)
        markdown_content = await document_processor.process_document(
            str(temp_path), write_output=False
        )
        token_count = _count_tokens(markdown_content)
        use_rag_fallback = (
            settings.RAG_ENGINE.lower() != "sat"
            and token_count > settings.MAX_UPLOAD_TOKENS
            and settings.ENABLE_UPLOAD_RAG_FALLBACK
        )

        legal_agent = getattr(runtime.app.state, "legal_agent", None) or LegalAgent()
        if not legal_agent.cohere_client:
            raise HTTPException(500, "Cohere client not initialized")

        system_prompt = _document_system_prompt(language, large_document=use_rag_fallback)

        if use_rag_fallback:
            temp_rag_dir = temp_dir / f"temp_rag_{runtime.uuid.uuid4().hex}"
            temp_rag_dir.mkdir(parents=True, exist_ok=True)
            try:
                from modules.rag.services.lightrag_engine import LegalRAGEngine

                temp_rag = LegalRAGEngine(working_dir=str(temp_rag_dir))
                temp_rag._ensure_initialized()
                await temp_rag.initialize_storages()
                await temp_rag.add_document(
                    content=markdown_content,
                    metadata={"filename": original_name, "source": "temp_upload"},
                    document_id="temp_doc",
                )
                rag_result = await temp_rag.query_with_rerank(
                    query, top_k=5, rerank_candidates=20
                )
                retrieved_context = rag_result.get(
                    "answer", "No se encontró información relevante"
                )
                user_message = (
                    f"FRAGMENTOS RECUPERADOS DEL DOCUMENTO:\n{retrieved_context}\n\n"
                    f"PREGUNTA:\n{query}\n\nResponde en {language}."
                )
                response = await legal_agent.cohere_client.chat(
                    model="command-r-plus-08-2024",
                    message=user_message,
                    preamble=system_prompt,
                    chat_history=[],
                    temperature=0.3,
                )
            except Exception as error:
                runtime._log_failure("temp_rag_failed", error, request)
                truncated_content = markdown_content[:10000]
                user_message = (
                    f"DOCUMENTO (TRUNCADO):\n{truncated_content}\n\n"
                    "[Nota: El documento es muy grande y se ha truncado. Esta respuesta puede no incluir toda la información.]\n\n"
                    f"PREGUNTA:\n{query}\n\nResponde en {language}."
                )
                response = await legal_agent.cohere_client.chat(
                    model="command-r-plus-08-2024",
                    message=user_message,
                    preamble=system_prompt,
                    chat_history=[],
                    temperature=0.3,
                )
            finally:
                shutil.rmtree(temp_rag_dir, ignore_errors=True)
        else:
            user_message = (
                f"DOCUMENTO:\n{markdown_content}\n\n"
                f"PREGUNTA:\n{query}\n\nResponde en {language}."
            )
            try:
                response = await legal_agent.cohere_client.chat(
                    model="command-r-plus-08-2024",
                    message=user_message,
                    preamble=system_prompt,
                    chat_history=[],
                    temperature=0.3,
                )
            except Exception as error:
                runtime._log_failure("document_cohere_failed", error, request)
                raise HTTPException(500, "Cohere API error")

        return {
            "success": True,
            "query": query,
            "response": response.text,
            "language": language,
            "document_type": (
                "image"
                if file_ext in LegalDocumentProcessor.SUPPORTED_IMAGE_FORMATS
                else "document"
            ),
            "original_filename": original_name,
            "processing_method": "rag_fallback" if use_rag_fallback else "long_context",
            "token_count": token_count,
        }
    except HTTPException:
        raise
    except Exception as error:
        runtime._log_failure("document_query_failed", error, request)
        raise HTTPException(500, "Document query failed")
    finally:
        _cleanup_paths(temp_path)
        await file.close()


@router.post("/upload-document")
@limiter.limit(settings.ADMIN_RATE_LIMIT)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    _auth: bool = Depends(verify_admin_api_key),
):
    """Sube y procesa un documento legal (PDF, imagen, DOCX, etc.) con Docling."""
    import main as runtime
    from ingestion.docling_processor import LegalDocumentProcessor

    file_ext = ""
    raw_path: Optional[Path] = None
    processed_path: Optional[Path] = None
    processed_created = False
    evidence_published = False
    try:
        supported_exts = (
            LegalDocumentProcessor.SUPPORTED_IMAGE_FORMATS
            | LegalDocumentProcessor.SUPPORTED_DOC_FORMATS
        )
        original_name, file_ext, server_name, raw_path = await save_validated_upload(
            file,
            runtime.RAW_PDFS_DIR,
            supported_exts=supported_exts,
            require_pdf_checks=True,
            id_factory=runtime.uuid.uuid4,
        )

        if file_ext == ".pdf":
            artifact = await convert_for_ingestion(
                runtime._get_pdf_processor(runtime.app), str(raw_path)
            )
            processed_content = artifact.markdown
        else:
            processed_content = await runtime._get_document_processor(
                runtime.app
            ).process_document(str(raw_path), write_output=False)

        processed_directory = runtime.PROCESSED_DIR.resolve()
        processed_directory.mkdir(parents=True, exist_ok=True)
        processed_path = processed_directory / f"{raw_path.stem}.md"
        with processed_path.open("x", encoding="utf-8", newline="") as handle:
            processed_created = True
            handle.write(processed_content)

        document_type = (
            "image"
            if file_ext in LegalDocumentProcessor.SUPPORTED_IMAGE_FORMATS
            else "document"
        )

        evidence = sat_result = None
        if file_ext == ".pdf":
            # Solo PDF entran al almacén de evidencia SAT.
            evidence = persist_source_evidence(
                raw_path,
                processed_path,
                processed_content,
                runtime.PROCESSED_DIR.parent / "source_evidence",
            )
            evidence_published = True
            sat_result = await asyncio.to_thread(
                lambda: runtime.stage_document(
                    runtime.sat_graph_store(),
                    evidence,
                    processed_content,
                    artifact.docling_document,
                ),
            )

        legacy_write = runtime.app.state.rag_engine is not None and (
            file_ext != ".pdf" or settings.SAT_INGESTION_LEGACY_RAG
        )
        if legacy_write:
            await runtime.app.state.rag_engine.add_document(
                processed_content,
                {
                    "filename": server_name,
                    "original_filename": original_name,
                    "title": original_name,
                    "document_type": "legal_pdf" if file_ext == ".pdf" else document_type,
                    "source": "upload-pdf" if file_ext == ".pdf" else "upload-document",
                },
                server_name,
            )

        if legacy_write and hasattr(runtime.app.state, "response_validator"):
            runtime.app.state.response_validator.cross_checker.update_documents(
                runtime.app.state.rag_engine.documents
            )

        return {
            "success": True,
            "filename": server_name,
            "original_filename": original_name,
            "file_type": document_type,
            "evidence_id": evidence.evidence_id if evidence else None,
            "graph_write_state": "unverified" if legacy_write else "pending_review",
            "sat_graph": sat_result,
            "message": f"{document_type.capitalize()} procesado correctamente con Docling",
        }
    except HTTPException:
        if not evidence_published:
            _cleanup_paths(raw_path, processed_path if processed_created else None)
        raise
    except Exception as error:
        if not evidence_published:
            _cleanup_paths(raw_path, processed_path if processed_created else None)
        runtime._log_failure("document_upload_failed", error, request)
        raise HTTPException(
            500,
            "PDF processing failed" if file_ext == ".pdf" else "Document processing failed",
        )
    finally:
        await file.close()


@router.post("/upload-pdf")
@limiter.limit(settings.ADMIN_RATE_LIMIT)
async def upload_pdf(
    request: Request,
    file: UploadFile = File(...),
    _auth: bool = Depends(verify_admin_api_key),
):
    """Sube y procesa un PDF legal con Docling (endpoint deprecado, usar /upload-document)."""
    if Path((file.filename or "").replace("\\", "/")).suffix.lower() != ".pdf":
        await file.close()
        raise HTTPException(400, "Only PDFs are accepted by this endpoint")
    return await upload_document(request, file, _auth)


@router.post("/batch-process")
@limiter.limit(settings.ADMIN_RATE_LIMIT)
async def batch_process_pdfs(
    request: Request, _auth: bool = Depends(verify_admin_api_key)
):
    """Procesa todos los PDFs del directorio raw_pdfs."""
    import main as runtime

    try:
        results = await runtime.app.state.ingestion_pipeline.process_all_pdfs()
        return {
            "success": True,
            "processed": results["processed_count"],
            "failed": results["failed_count"],
            "details": results["details"],
        }
    except Exception as error:
        runtime._log_failure("batch_processing_failed", error, request)
        raise HTTPException(500, "Batch processing failed")


@router.get("/documents")
async def list_documents(_auth: bool = Depends(verify_admin_api_key)):
    import main as runtime

    if runtime.app.state.rag_engine is None:
        raise HTTPException(
            409, "Use the SAT corpus review to list documents in SAT mode"
        )
    try:
        docs = await runtime.app.state.rag_engine.list_documents()
        return {"success": True, "documents": docs}
    except Exception as error:
        runtime._log_failure("document_listing_failed", error)
        raise HTTPException(500, "Failed to list documents")
