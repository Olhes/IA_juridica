import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_keyword_fallback_reports_matching_source(rag):
    result = await rag.query("tasa licencia municipal")
    assert result["method"] == "fallback_keyword"
    assert result["sources"] == ["licencia-2019.md"]
    assert 0 < result["confidence"] <= 1


@pytest.mark.asyncio
async def test_keyword_fallback_no_match_is_explicit(rag):
    result = await rag.query("inmueble herencia sucesion")
    assert result["method"] == "fallback_no_match"
    assert result["sources"] == []
    assert result["confidence"] == 0


@pytest.mark.asyncio
async def test_local_rerank_returns_chunk_shape(rag):
    result = await rag.query_with_rerank("tasa licencia municipal", top_k=1)
    assert result["method"] == "fallback_keyword_rerank"
    assert result["total_candidates"] == 2
    assert len(result["documents"]) == len(result["rerank_scores"]) == 1
    assert result["documents"][0]["id"] == "new_chunk_0"
    assert result["sources"] == ["licencia-2024.md"]


def test_chunking_is_sentence_length_based_not_hierarchical(rag):
    text = "Artículo primero. Artículo segundo. Artículo tercero."
    chunks = rag._chunk_content(text, chunk_size=35)
    assert len(chunks) >= 2
    assert all(isinstance(chunk, str) and chunk for chunk in chunks)
    assert "Artículo primero" in chunks[0]


@pytest.mark.asyncio
async def test_empty_corpus_has_distinct_query_and_rerank_fallbacks(rag):
    rag.documents = {}
    plain = await rag.query("tasa licencia")
    ranked = await rag.query_with_rerank("tasa licencia")
    assert (plain["method"], plain["sources"], plain["confidence"]) == ("fallback_no_match", [], 0.0)
    assert (ranked["method"], ranked["documents"], ranked["sources"]) == ("no_documents", [], [])


@pytest.mark.asyncio
async def test_failed_lightrag_insert_still_stores_local_document(rag, monkeypatch):
    import modules.rag.services.lightrag_engine as module

    monkeypatch.setattr(module, "LIGHTRAG_AVAILABLE", True)
    rag.rag = SimpleNamespace(ainsert=AsyncMock(side_effect=RuntimeError("offline failure")))
    rag._storages_initialized = True
    rag.working_dir.mkdir()
    await rag.add_document("Regla local de licencia.", {"filename": "regla.md"}, "rule")
    assert rag.rag.ainsert.await_count == 1
    assert rag.documents["rule"]["metadata"]["filename"] == "regla.md"
    assert "Regla local" in rag._documents_store_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_failed_cohere_rerank_uses_local_scores(rag, monkeypatch):
    import modules.rag.services.lightrag_engine as module

    monkeypatch.setattr(module, "COHERE_AVAILABLE", True)
    rag.cohere_client = SimpleNamespace(rerank=AsyncMock(side_effect=RuntimeError("offline failure")))
    result = await rag.query_with_rerank("tasa licencia municipal", top_k=1)
    rag.cohere_client.rerank.assert_awaited_once()
    assert result["method"] == "fallback_keyword_rerank"
    assert result["sources"] == ["licencia-2024.md"]
