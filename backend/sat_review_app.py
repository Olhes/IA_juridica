"""Independent, loopback-only SAT editorial workstation (no chat/LLM startup).

Launch: uv run python backend/sat_review_app.py [--open] [--port 8010]
An ephemeral capability bootstraps an HttpOnly session; it is never stored in JS.
"""
import argparse
import secrets
import threading
import webbrowser
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
import uvicorn

load_dotenv(Path(__file__).parent / ".env")
from config.settings import settings
from services.quality_access import require_quality_admin
from services.sat_corpus_routes import router as review_router
from services.sat_api import router as api_router


def create_local_app(token):
    app = FastAPI(title="SAT Corpus · estación local de revisión", docs_url=None, redoc_url=None)
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
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    app.include_router(review_router)
    app.include_router(api_router)
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--db", type=Path, help="Override for isolated testing; defaults to the chat SAT_GRAPH_PATH")
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    if args.db:
        settings.SAT_GRAPH_PATH = str(args.db.resolve())
    if not Path(settings.SAT_GRAPH_PATH).is_file():
        parser.error("No existe SAT_GRAPH_PATH; no se creará una base vacía")
    token = secrets.token_urlsafe(32)
    url = f"http://127.0.0.1:{args.port}/local-session/{token}"
    print(f"Editor independiente SAT. Base: {settings.SAT_GRAPH_PATH}\nAcceso local (privado): {url}", flush=True)
    if args.open:
        timer = threading.Timer(1.5, lambda: webbrowser.open(url))
        timer.daemon = True
        timer.start()
    uvicorn.run(create_local_app(token), host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
