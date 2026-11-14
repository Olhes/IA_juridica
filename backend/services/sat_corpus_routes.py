"""Authenticated editor APIs; static shell contains no corpus data or secrets."""
import asyncio
from hashlib import sha256
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response

from config.settings import settings
from ingestion.sat_graph.runtime import runtime_sat_store
from services.quality_access import require_quality_admin
from services.sat_corpus import CandidateShelf, CorpusEditor, Conflict, Publication, TextEdit, candidate_already_published, replace_text

router = APIRouter(prefix="/sat-graph/review", tags=["SAT corpus review"])
ASSETS = Path(__file__).resolve().parents[1] / "static" / "sat-review"
REVIEWS = Path(__file__).resolve().parents[1] / "docs" / "sat_reviews"
# En contenedor la raíz del repo no es escribible: SAT_CANDIDATES_DIR la redirige
# a un volumen persistente para no perder candidatos en cada despliegue.
CANDIDATES = (
    Path(settings.SAT_CANDIDATES_DIR).resolve()
    if settings.SAT_CANDIDATES_DIR
    else Path(__file__).resolve().parents[2] / "temp" / "sat-corpus-work"
)


def editor():
    # Always the identical configured database used by SATChatRetriever.
    return CorpusEditor(runtime_sat_store())


def candidate_shelf():
    return CandidateShelf(CANDIDATES)


def candidate_is_reference(item, graph):
    official_id = item.get("official_id")
    return (item["reference_only"]
            or not any(n["type"] == "Resource" and n["id"] == official_id and n.get("kind") == "norm"
                       for n in graph["nodes"])
            or any(n["type"] == "Work" and n.get("resource_id") == official_id for n in graph["nodes"]))


def review_document(resource_id):
    if resource_id.startswith("candidate:"):
        item = candidate_shelf().get(resource_id)
        graph = editor().store.export()
        published = any(candidate_already_published(item, n) for n in graph["nodes"])
        return {**item, "published": published, "editable": not published,
                "reference_only": candidate_is_reference(item, graph)}
    return editor().get(resource_id)


async def call(fn):
    try:
        return await asyncio.to_thread(fn)
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("", include_in_schema=False)
async def page():
    return FileResponse(ASSETS / "index.html", headers={
        "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; frame-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'self'",
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/assets/{name}", include_in_schema=False)
async def asset(name: str):
    if name not in {"editor.js", "editor.css", "favicon.svg"}:
        raise HTTPException(404)
    return FileResponse(ASSETS / name, headers={"Cache-Control": "no-cache"})


@router.get("/documents", dependencies=[Depends(require_quality_admin)])
async def list_documents():
    return await call(lambda: {"documents": editor().list(), "chat_engine": settings.RAG_ENGINE.lower()})


@router.get("/candidates", dependencies=[Depends(require_quality_admin)])
async def list_candidates():
    def inventory():
        graph = editor().store.export()
        revisions = [n for n in graph["nodes"] if n["type"] == "DocumentaryRevision"]
        return [{**item, "published": any(candidate_already_published(item, n) for n in revisions),
                 "reference_only": candidate_is_reference(item, graph)}
                for item in candidate_shelf().list()]
    return await call(inventory)


@router.get("/documents/{resource_id}", dependencies=[Depends(require_quality_admin)])
async def get_document(resource_id: str):
    return await call(lambda: review_document(resource_id))


@router.post("/preview", dependencies=[Depends(require_quality_admin)])
async def preview(edit: TextEdit):
    return await call(lambda: replace_text(edit).model_dump())


@router.post("/documents/{resource_id}")
async def publish(resource_id: str, publication: Publication, request: Request,
                  actor: str = Depends(require_quality_admin)):
    if request.headers.get("X-SAT-Review") != "1":
        raise HTTPException(403, "Falta confirmación del editor")
    def apply_review():
        if resource_id.startswith("candidate:"):
            shelf = candidate_shelf()
            candidate = shelf.get(resource_id)
            shelf.pdf_path(candidate)
            return editor().apply(resource_id, publication, actor, candidate=candidate)
        return editor().apply(resource_id, publication, actor)
    return await call(apply_review)


@router.get("/documents/{resource_id}/markdown", dependencies=[Depends(require_quality_admin)])
async def markdown(resource_id: str):
    doc = await call(lambda: review_document(resource_id))
    if not doc["edition"]:
        raise HTTPException(404, "Sin edición documental")
    return Response(doc["edition"]["markdown"], media_type="text/markdown",
                    headers={"Content-Disposition": 'attachment; filename="corpus-sat.md"'})


@router.get("/documents/{resource_id}/pdf", dependencies=[Depends(require_quality_admin)])
async def pdf(resource_id: str):
    def locate():
        doc = review_document(resource_id)
        if doc.get("candidate") or doc.get("candidate_pdf"):
            name = doc.get("candidate_pdf") or doc.get("pdf_name")
            if not doc.get("candidate") and doc.get("candidate_pdf"):
                # Published reference PDFs ship with the corpus; candidate work stays local.
                directory = (REVIEWS / "published-references").resolve()
                bundled = (directory / name).resolve()
                if (bundled.is_relative_to(directory) and bundled.is_file()
                        and "pdf-sha256-" + sha256(bundled.read_bytes()).hexdigest() == doc["evidence_id"]):
                    return bundled
            return candidate_shelf().pdf_path({**doc, "pdf_name": name})
        if not doc["directory"]:
            raise ValueError("PDF local no disponible")
        path = (REVIEWS / doc["directory"] / "source.pdf").resolve()
        if not path.is_relative_to(REVIEWS.resolve()) or not path.is_file():
            raise ValueError("PDF local no disponible")
        if "pdf-sha256-" + sha256(path.read_bytes()).hexdigest() != doc["evidence_id"]:
            raise ValueError("El PDF no coincide con la evidencia del grafo")
        return path
    return FileResponse(await call(locate), media_type="application/pdf")
