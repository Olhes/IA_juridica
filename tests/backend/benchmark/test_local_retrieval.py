from time import perf_counter

import pytest


@pytest.mark.parametrize("corpus_size", [2, 32, 128])
@pytest.mark.asyncio
async def test_offline_keyword_retrieval_reports_elapsed_without_speed_gate(rag, corpus_size):
    for index in range(corpus_size - 2):
        rag.documents[f"extra-{index}"] = {
            "content": "Regla ajena de visitas.",
            "chunks": ["Regla ajena de visitas."],
            "metadata": {"filename": f"extra-{index}.md"},
        }
    iterations = 25
    start = perf_counter()
    for _ in range(iterations):
        result = await rag.query_with_rerank("tasa licencia municipal", top_k=1, rerank_candidates=corpus_size)
        assert result["method"] == "fallback_keyword_rerank"
        assert len(result["documents"]) == 1
        assert result["sources"] == ["licencia-2024.md"]
        assert result["total_candidates"] == 2  # Irrelevant chunks are filtered before reranking.
    elapsed = perf_counter() - start
    assert elapsed >= 0
    print(f"local_keyword_rerank corpus_size={corpus_size} iterations={iterations} seconds_per_query={elapsed / iterations:.6f}")
