"""Fixtures exclusivos de las suites Python del backend."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

# Fixtures HTTP y recuperación local (sin lifespan ni servicios externos).


@pytest.fixture
def legal_corpus():
    # Synthetic, conflicting rules: dates are fixture metadata, not a supported selector.
    return {
        "old": {
            "content": "La tasa de licencia municipal es diez unidades. Vigencia 2019-01-01.",
            "chunks": ["La tasa de licencia municipal es diez unidades."],
            "metadata": {
                "filename": "licencia-2019.md",
                "effective_date": "2019-01-01",
            },
        },
        "new": {
            "content": "La tasa de licencia municipal es veinte unidades. Vigencia 2024-01-01.",
            "chunks": ["La tasa de licencia municipal es veinte unidades."],
            "metadata": {
                "filename": "licencia-2024.md",
                "effective_date": "2024-01-01",
            },
        },
    }


@pytest.fixture
def rag(monkeypatch, tmp_path, legal_corpus):
    from config.settings import settings
    from modules.rag.services.lightrag_engine import LegalRAGEngine

    monkeypatch.setattr(settings, "LOAD_LOCAL_KG", False)
    engine = LegalRAGEngine(working_dir=str(tmp_path / "kg"))
    engine.documents = legal_corpus
    engine._ensure_initialized = lambda: None
    engine.cohere_client = None
    return engine


@pytest.fixture
def api(monkeypatch):
    import main
    from config.settings import settings
    from security import limiter

    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    # SlowAPI conserva una copia de este indicador cuando su instancia única se crea al importar el módulo.
    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setattr(settings, "ADMIN_ENDPOINTS_ENABLED", True)
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "offline-admin-key")
    optimizer = MagicMock()
    optimizer.get_cached.return_value = None
    monkeypatch.setattr(main.app.state, "llm_optimizer", optimizer, raising=False)
    monkeypatch.setattr(
        main.app.state,
        "rag_engine",
        SimpleNamespace(
            get_cache_revision=lambda: "offline-fixture-v1",
            query_with_rerank=AsyncMock(
                return_value={"documents": [], "method": "no_documents"}
            ),
        ),
        raising=False,
    )
    client = TestClient(main.app)  # No lifespan: no Redis/Postgres/LLM startup.
    yield client, main, optimizer
    client.close()
