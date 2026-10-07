"""Fragmentación local y embeddings simulados; ningún SDK hace llamadas reales."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from context.chunking_strategies import ContextualChunker, LegalChunkingStrategy
from config.settings import settings


@pytest.mark.parametrize(
    "content, kind",
    [
        ("Código civil\nArtículo 1. Texto A\nArtículo 2. Texto B", "codigo"),
        ("Demanda de prueba\nNOMBRE: Ejemplo\nPETITORIO: Texto", "demanda"),
        ("# Manual sintético\nTexto A\n## Sección siguiente\nTexto B", "manual"),
        ("Texto sintético sin estructura", "general"),
    ],
)
def test_legal_chunking_detects_structure_and_preserves_order(content, kind):
    chunks = LegalChunkingStrategy().chunk_by_legal_structure(content)
    assert chunks
    assert all(chunk["document_type"] == kind for chunk in chunks)
    assert [chunk["position"] for chunk in chunks] == list(range(len(chunks)))
    assert [chunk["chunk_id"] for chunk in chunks] == [
        f"{kind}_{i+1}" for i in range(len(chunks))
    ]
    assert all(chunk["content"] in content for chunk in chunks)
    assert all(chunk["word_count"] == len(chunk["content"].split()) for chunk in chunks)
    if kind == "codigo":
        assert [chunk["article_number"] for chunk in chunks] == ["1", "2"]
    if kind == "manual":
        assert [chunk["title_level"] for chunk in chunks] == [1, 2]
    if kind == "demanda":
        assert any(chunk["is_form_field"] for chunk in chunks)


@pytest.mark.parametrize("kind", ["CODIGO", "MANUAL", "GENERAL"])
def test_chunking_falls_back_to_paragraphs_and_skips_empty_content(kind):
    strategy = LegalChunkingStrategy()
    assert strategy.chunk_by_legal_structure("\n\n", kind) == []
    paragraphs = "A" * 700 + "\n\n\n\n" + "B" * 700
    chunks = strategy.chunk_by_legal_structure(paragraphs, kind)
    assert [chunk["content"] for chunk in chunks] == ["A" * 700, "B" * 700]
    assert [chunk["position"] for chunk in chunks] == [0, 1]


@pytest.mark.parametrize(
    "text, urgency",
    [
        ("Urgente protección comisaría comunidad rural ayllu", "high"),
        ("Importante alimentos juzgado", "medium"),
        ("Información general", "low"),
    ],
)
def test_chunk_metadata_records_theme_urgency_and_cultural_indicators(text, urgency):
    chunk = LegalChunkingStrategy().chunk_by_legal_structure(text)[0]
    assert chunk["legal_context"]["urgency"] == urgency
    if "comisaría" in text:
        assert chunk["legal_context"]["legal_theme"] == "violencia"
        assert "comisaría" in chunk["legal_context"]["entities"]
        assert chunk["cultural_relevance"]["quechua_terms"]["present"] is True
    if urgency == "low":
        assert all(
            value["score"] == 0 for value in chunk["cultural_relevance"].values()
        )


def test_contextual_chunker_attaches_document_metadata_and_computes_stats():
    chunker = ContextualChunker()
    metadata = {"document_type": "codigo", "filename": "synthetic.md"}
    chunks = chunker.process_document(
        "Artículo 1. Alimentos de prueba\nArtículo 2. Texto", metadata
    )
    assert all(chunk["document_metadata"] == metadata for chunk in chunks)
    stats = chunker.get_chunking_stats(chunks)
    assert stats["total_chunks"] == 2
    assert stats["total_words"] == sum(chunk["word_count"] for chunk in chunks)
    assert stats["avg_chunk_size"] == stats["total_words"] / 2
    assert stats["chunk_types"] == {"article": 2}
    assert stats["legal_themes"] == {"alimentos": 1}
    assert chunker.get_chunking_stats([]) == {"total_chunks": 0}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "available, fail", [(False, False), (True, False), (True, True)]
)
async def test_embeddings_are_batched_and_provider_failure_preserves_chunks(
    monkeypatch, available, fail
):
    chunker = ContextualChunker()
    chunks = [{"content": str(i)} for i in range(3)]
    monkeypatch.setattr(chunker, "process_document", lambda *_: chunks)
    embed = AsyncMock(
        side_effect=(
            RuntimeError("synthetic")
            if fail
            else [
                SimpleNamespace(embeddings=SimpleNamespace(float_=[[1], [2]])),
                SimpleNamespace(embeddings=SimpleNamespace(float_=[[3]])),
            ]
        )
    )
    monkeypatch.setattr(
        chunker,
        "_get_cohere_client",
        lambda: SimpleNamespace(embed=embed) if available else None,
    )
    monkeypatch.setattr(settings, "EMBEDDING_BATCH_SIZE", 2)
    result = await chunker.chunk_and_embed("synthetic", {})
    assert result is chunks
    if available and not fail:
        assert [chunk["embedding"] for chunk in result] == [[1], [2], [3]]
        assert [call.kwargs["texts"] for call in embed.await_args_list] == [
            ["0", "1"],
            ["2"],
        ]
        assert all(
            call.kwargs["input_type"] == "search_document"
            for call in embed.await_args_list
        )
    else:
        assert all("embedding" not in chunk for chunk in result)


def test_document_processing_propagates_failure_without_partial_result(monkeypatch):
    chunker = ContextualChunker()
    monkeypatch.setattr(
        chunker.strategy,
        "chunk_by_legal_structure",
        Mock(side_effect=ValueError("synthetic")),
    )
    with pytest.raises(ValueError, match="synthetic"):
        chunker.process_document("synthetic", {})
