from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from evaluation.harness import nvidia_voyage, runner


@pytest.mark.asyncio
async def test_nvidia_voyage_uses_retrieval_without_gold_or_judge(monkeypatch, tmp_path):
    from config.settings import settings
    from pydantic import SecretStr

    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    monkeypatch.setattr(settings, "VOYAGE_API_KEY", SecretStr("test-voyage"))
    calls = []

    class Voyage:
        def __init__(self, *args, **kwargs):
            pass

        def embed(self, groups, *, input_type):
            calls.append(("embed", input_type))
            return [[[1.0, 0.0]] for _ in groups], {}

        def rerank(self, query, documents, *, top_k):
            calls.append(("rerank", top_k))
            return [(i, 1.0) for i in range(top_k)], {}

    class Client:
        def __init__(self, **kwargs):
            pass

        async def post(self, url, *, headers, json):
            calls.append(("nvidia", url, json))
            return SimpleNamespace(raise_for_status=lambda: None,
                                   json=lambda: {"choices": [{"message": {"content": "respuesta"}}]})

        async def aclose(self):
            pass

    monkeypatch.setattr(nvidia_voyage, "VoyageProvider", Voyage)
    monkeypatch.setattr(nvidia_voyage.httpx, "AsyncClient", Client)
    corpus = SimpleNamespace(segments={"a": SimpleNamespace(id="a", doc_id="doc", text="plazo de prueba")})
    sleep = AsyncMock()
    monkeypatch.setattr(nvidia_voyage.asyncio, "sleep", sleep)
    answer = nvidia_voyage.build_answer_fn(corpus, tmp_path / "cache.sqlite", delay_seconds=15)
    result = await answer(SimpleNamespace(query="plazo de prueba"), 0)
    assert result.text == "respuesta" and result.contexts == ["plazo de prueba"]
    assert [c[0] for c in calls] == ["embed", "embed", "rerank", "nvidia"]
    assert calls[-1][1] == nvidia_voyage.URL
    assert calls[-1][2]["model"] == nvidia_voyage.MODEL
    await answer(SimpleNamespace(query="otra consulta"), 0)
    sleep.assert_awaited_once_with(15)
    await answer.close()


def test_nvidia_voyage_requires_bounded_no_judge_cli():
    with pytest.raises(SystemExit):
        runner.main(["legal_qa", "--provider", "nvidia-voyage"])
    with pytest.raises(SystemExit):
        runner.main(["legal_qa", "--provider", "nvidia-voyage", "--limit", "1", "--judge", "deepeval"])


@pytest.mark.asyncio
async def test_ragas_string_similarity_uses_reference_without_llm(monkeypatch):
    import sys
    import types

    class Scorer:
        async def ascore(self, *, reference, response):
            assert reference == "hecho esperado" and response == "respuesta"
            return SimpleNamespace(value=0.5)

    monkeypatch.setitem(sys.modules, "ragas", types.ModuleType("ragas"))
    monkeypatch.setitem(sys.modules, "ragas.metrics", types.ModuleType("ragas.metrics"))
    collection = types.ModuleType("ragas.metrics.collections")
    collection.NonLLMStringSimilarity = Scorer
    monkeypatch.setitem(sys.modules, "ragas.metrics.collections", collection)
    case = SimpleNamespace(id="x", required_facts=[SimpleNamespace(text="hecho esperado")])
    result = await nvidia_voyage.ragas_string_similarity([case], [{"case_id": "x", "answer": {"text": "respuesta"}}])
    assert result == {"available": True, "value": 0.5, "n": 1}
