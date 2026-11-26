"""Validate the Render free-tier Blueprint against production Settings rules."""

from pathlib import Path

import yaml

from config.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]
RENDER_YAML = REPO_ROOT / "render.yaml"
RENDER_DOCKERFILE = REPO_ROOT / "deploy" / "render" / "Dockerfile"
RENDER_ENTRYPOINT = REPO_ROOT / "deploy" / "render" / "entrypoint.sh"


def _load_blueprint():
    return yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))


def test_render_blueprint_defines_free_backend_and_private_keyvalue():
    blueprint = _load_blueprint()
    services = {svc["name"]: svc for svc in blueprint["services"]}
    assert set(services) == {"ia-juridica-backend", "ia-juridica-cache"}

    web = services["ia-juridica-backend"]
    assert web["type"] == "web"
    assert web["runtime"] == "docker"
    assert web["plan"] == "free"
    assert web["dockerfilePath"] == "./deploy/render/Dockerfile"
    assert web["dockerContext"] == "."
    assert web["healthCheckPath"] == "/ready"
    assert (REPO_ROOT / web["dockerfilePath"].lstrip("./")).is_file()

    cache = services["ia-juridica-cache"]
    assert cache["type"] == "keyvalue"
    assert cache["plan"] == "free"
    assert cache["ipAllowList"] == []

    env = {item["key"]: item for item in web["envVars"]}
    assert env["REDIS_URL"]["fromService"] == {
        "type": "keyvalue",
        "name": "ia-juridica-cache",
        "property": "connectionString",
    }
    assert env["RATE_LIMIT_STORAGE_URI"]["fromService"] == env["REDIS_URL"]["fromService"]


def test_render_blueprint_env_passes_production_settings_validation(monkeypatch):
    monkeypatch.setattr(Settings, "_create_directories", lambda self: None)
    blueprint = _load_blueprint()
    web = next(s for s in blueprint["services"] if s["name"] == "ia-juridica-backend")

    for entry in web["envVars"]:
        key = entry["key"]
        if "value" in entry:
            monkeypatch.setenv(key, str(entry["value"]))
        elif entry.get("generateValue"):
            monkeypatch.setenv(key, "r" * 48)
        elif "fromService" in entry:
            monkeypatch.setenv(key, "redis://ia-juridica-cache:6379")
        elif key == "COHERE_API_KEY":
            monkeypatch.setenv(key, "synthetic-cohere-key")
        elif key == "VOYAGE_API_KEY":
            monkeypatch.setenv(key, "")

    settings = Settings(_env_file=None)
    report = settings.validate_configuration()
    assert report["valid"] is True, report["issues"]
    assert settings.is_production() is True
    assert settings.session_cookie_secure() is True
    assert settings.CORS_ORIGINS == ["https://ia-juridica-pe.vercel.app"]
    assert settings.GOOGLE_FRONTEND_CALLBACK_URI == "https://ia-juridica-pe.vercel.app/auth/callback"
    assert settings.RAG_ENGINE == "sat"
    assert settings.COHERE_THINKING_ENABLED is False


def test_render_entrypoint_has_lf_endings_and_embedded_and_external_paths():
    raw = RENDER_ENTRYPOINT.read_bytes()
    assert b"\r\n" not in raw, "entrypoint.sh must use LF line endings for Linux containers"
    text = raw.decode("utf-8")
    assert "rotate_embedded_root_password" in text
    assert "export SURREAL_PASSWORD=" in text
    assert "trap - TERM INT EXIT" in text
    assert "bootstrap_sat_corpus" in text
    assert "exec /app/.venv/bin/uvicorn" in text

    dockerfile = RENDER_DOCKERFILE.read_text(encoding="utf-8")
    assert "surrealdb/surrealdb:v4.0.1" in dockerfile
    assert "scripts.bootstrap_sat_corpus" in dockerfile
    assert "/app/docs/raw_pdfs" in dockerfile
    assert "/app/docs/processed" in dockerfile
    assert "/app/docs/knowledge_graph" in dockerfile
    assert 'cd /app/backend || exit 1;' in dockerfile
    assert 'if [ "$rc" -ne 0 ]; then' in dockerfile
    assert "USER appuser" in dockerfile
