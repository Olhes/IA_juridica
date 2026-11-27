"""Independent, loopback-only SAT editorial workstation (no chat/LLM startup).

Launch: uv run python backend/sat_review_app.py [--open] [--port 8011]
An ephemeral capability bootstraps an HttpOnly session; it is never stored in JS.
"""
import argparse
import secrets
import threading
import webbrowser
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import RedirectResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
import uvicorn

load_dotenv(Path(__file__).parent / ".env")
from ingestion.sat_graph.runtime import runtime_sat_store
from services.quality_access import require_quality_admin
from services.sat_corpus_routes import router as review_router
from services.sat_api import router as api_router
from services.sat_provenance_routes import router as provenance_router
from services.sat_temporal_routes import router as temporal_router


def create_local_app(token):
    app = FastAPI(title="SAT Corpus · estación local de revisión", docs_url=None, redoc_url=None)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    async def local_session(request: Request):
        session = request.cookies.get("sat_editor_session", "")
        if not secrets.compare_digest(session, token):
            raise HTTPException(403, "Abra el enlace local de acceso impreso al iniciar el editor")
        return "local-corpus-reviewer"

    app.dependency_overrides[require_quality_admin] = local_session

    @app.get("/local-session/{access}", include_in_schema=False)
    async def bootstrap(access: str):
        if not secrets.compare_digest(access, token):
            raise HTTPException(403)
        response = RedirectResponse("/sat-graph/review", status_code=303)
        response.set_cookie("sat_editor_session", token, httponly=True, samesite="strict", path="/", max_age=43200)
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.middleware("http")
    async def private_response(request, call_next):
        response = await call_next(request)
        if not request.url.path.startswith("/sat-graph/review/assets/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    app.include_router(review_router)
    app.include_router(api_router)
    app.include_router(provenance_router)
    app.include_router(temporal_router)
    return app


DEFAULT_PORT = 8011  # 8000 = FastAPI backend, 8010 = SurrealDB host port


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    try:
        store = runtime_sat_store()
        store.require_ready()
    except Exception:
        parser.error("No se pudo abrir el corpus SAT. Verifica SurrealDB y que el corpus esté cargado.")
    token = secrets.token_urlsafe(32)
    url = f"http://127.0.0.1:{args.port}/local-session/{token}"
    print(f"Editor independiente SAT. Base: SurrealDB\nAcceso local (privado): {url}", flush=True)
    if args.open:
        timer = threading.Timer(1.5, lambda: webbrowser.open(url))
        timer.daemon = True
        timer.start()
    uvicorn.run(create_local_app(token), host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
