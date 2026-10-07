"""Executable scenarios inspired by temporal conflicts in SAT-Graph, not a CTV implementation."""

import pytest


@pytest.mark.asyncio
async def test_given_conflicting_rules_when_keyword_query_then_source_is_reported(rag):
    result = await rag.query("tasa licencia municipal")
    assert result["sources"] == ["licencia-2019.md"]
    assert "diez unidades" in result["answer"]


@pytest.mark.xfail(strict=True, reason="Keyword rerank ignores effective_date; no temporal CTV selector exists")
@pytest.mark.asyncio
async def test_given_newer_effective_rule_when_reranked_then_new_rule_should_win(rag):
    result = await rag.query_with_rerank("tasa licencia municipal", top_k=1)
    assert result["sources"] == ["licencia-2024.md"]
    # Swapping effective dates must change the winner: a hash tie is not a temporal selector.
    rag.documents["old"]["metadata"]["effective_date"] = "2030-01-01"
    result = await rag.query_with_rerank("tasa licencia municipal", top_k=1)
    assert result["sources"] == ["licencia-2019.md"]


@pytest.mark.xfail(strict=True, reason="Local retrieval returns source metadata but no modifying Action evidence chain")
@pytest.mark.asyncio
async def test_given_rule_amended_by_action_when_retrieved_then_amendment_is_traceable(rag):
    # Una modificación sintética en el texto no constituye por sí misma un vínculo de procedencia verificado.
    rag.documents["new"]["content"] += " Resolución 42-2024 modifica la regla de 2019."
    rag.documents["new"]["chunks"] = [rag.documents["new"]["content"]]
    result = await rag.query_with_rerank("Resolución 42-2024 modifica", top_k=1)
    assert result["documents"][0]["document_id"] == "new"
    assert result["documents"][0]["action_provenance"] == [
        {"action": "amends", "target": "licencia-2019.md", "instrument": "Resolución 42-2024"}
    ]
