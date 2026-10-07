"""Configuración validada sin cargar .env ni crear directorios fuera del test."""

import pytest
from config.settings import Settings


def test_default_app_identity_is_branch_not_invented_release():
    assert Settings.model_fields["APP_VERSION"].default == "v8"


def configured(monkeypatch, **overrides):
    monkeypatch.setattr(Settings, "_create_directories", lambda self: None)
    values = dict(
        _env_file=None,
        COHERE_API_KEY="synthetic",
        OPENAI_API_KEY="",
        ENVIRONMENT="production",
        DEBUG=False,
        ANONYMOUS_SESSION_SECRET="x" * 32,
        DATABASE_PASSWORD="synthetic",
        CORS_ORIGINS=["https://example.invalid"],
        CORS_ALLOW_METHODS=["GET", "POST"],
        CORS_ALLOW_HEADERS=["Content-Type"],
        RATE_LIMIT_STORAGE_URI="redis://example.invalid:6379",
        ADMIN_ENDPOINTS_ENABLED=False,
        ANONYMOUS_SESSION_COOKIE_SAMESITE="lax",
        EMBEDDING_DIM=1024,
    )
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize(
    "overrides, expected",
    [
        ({"ANONYMOUS_SESSION_SECRET": "short"}, "ANONYMOUS_SESSION_SECRET"),
        ({"CORS_ORIGINS": ["*"]}, "CORS_ORIGINS"),
        ({"CORS_ALLOW_METHODS": ["*"]}, "CORS methods/headers"),
        ({"RATE_LIMIT_STORAGE_URI": "memory://"}, "RATE_LIMIT_STORAGE_URI"),
        ({"ADMIN_ENDPOINTS_ENABLED": True, "ADMIN_API_KEY": None}, "ADMIN_API_KEY"),
        ({"ANONYMOUS_SESSION_COOKIE_SAMESITE": "invalid"}, "SAMESITE"),
        ({"COHERE_API_KEY": ""}, "COHERE_API_KEY"),
    ],
)
def test_production_rejects_insecure_or_incomplete_settings(
    monkeypatch, overrides, expected
):
    result = configured(monkeypatch, **overrides).validate_configuration()
    assert result["valid"] is False
    assert any(expected in issue for issue in result["issues"])


def test_production_config_preserves_secure_cookies_and_hides_docs_by_default(
    monkeypatch,
):
    settings = configured(monkeypatch)
    assert settings.validate_configuration()["valid"] is True
    assert settings.session_cookie_secure() is True
    assert settings.docs_enabled() is False
    explicit = configured(monkeypatch, API_DOCS_ENABLED=True)
    assert explicit.docs_enabled() is True


def test_development_samesite_none_requires_explicit_secure_cookie(monkeypatch):
    settings = configured(
        monkeypatch,
        ENVIRONMENT="development",
        ANONYMOUS_SESSION_COOKIE_SAMESITE="none",
        ANONYMOUS_SESSION_COOKIE_SECURE=False,
    )
    assert settings.docs_enabled() is True
    assert any(
        "SameSite=None" in issue
        for issue in settings.validate_configuration()["issues"]
    )
    assert (
        configured(
            monkeypatch,
            ENVIRONMENT="development",
            ANONYMOUS_SESSION_COOKIE_SAMESITE="none",
            ANONYMOUS_SESSION_COOKIE_SECURE=True,
        ).validate_configuration()["valid"]
        is True
    )


def test_provider_config_exports_and_embedding_warning_match_settings(monkeypatch):
    settings = configured(monkeypatch, EMBEDDING_DIM=512)
    assert settings.get_cohere_config()["llm_model"] == settings.COHERE_LLM_MODEL
    assert settings.get_openai_config()["model"] == settings.OPENAI_MODEL
    assert settings.get_rag_config()["working_dir"] == settings.KNOWLEDGE_GRAPH_DIR
    result = settings.validate_configuration()
    assert result["valid"] is True
    assert any("512" in warning for warning in result["warnings"])
