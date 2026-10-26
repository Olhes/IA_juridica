"""Contrato REST con httpx.MockTransport: cero solicitudes reales/costes."""

from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3

import httpx
import pytest

from retrieval.voyage import VoyageError, VoyageProvider, VoyageCacheMiss


def response_for(request):
    body = json.loads(request.content)
    if request.url.path.endswith("rerank"):
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": i, "relevance_score": 1 / (i + 1)}
                    for i in range(body["top_k"])
                ],
                "usage": {"total_tokens": 12},
            },
        )
    return httpx.Response(
        200,
        json={
            "data": [
                {
                    "index": i,
                    "data": [
                        {"index": j, "embedding": [1.0] + [0.0] * 255, "text": text}
                        for j, text in enumerate(group)
                    ],
                }
                for i, group in enumerate(body["inputs"])
            ],
            "usage": {"total_tokens": 10},
            "model": "voyage-context-4",
        },
    )


def provider(tmp_path, handler=response_for, **kwargs):
    options = dict(
        requests_per_minute=10000, token_bound_per_minute=1000000, max_429_retries=0
    )
    options.update(kwargs)
    return VoyageProvider(
        "test-secret-never-log",
        tmp_path / "cache.db",
        dimension=256,
        transport=httpx.MockTransport(handler),
        **options,
    )


def test_context_cache_covers_group_order_type_and_dimension(tmp_path):
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return response_for(request)

    client = provider(tmp_path, handler)
    groups = [["Contenido A", "Contenido B"]]
    first, usage = client.embed(groups)
    cached, hit = client.embed(groups)
    assert first == cached and usage["tokens"] == 10 and hit["cache_hits"] == 1
    client.embed([["Contenido A", "Contexto cambiado"]])
    client.embed([["Contenido A"]], input_type="query")
    assert len(requests) == 3
    assert (
        requests[0]["inputs"] == groups and requests[0]["enable_auto_chunking"] is False
    )
    assert requests[0]["output_dimension"] == 256
    assert client.usage()["reported_tokens"] == 30
    with sqlite3.connect(client.path) as db:
        stored = str(db.execute("SELECT * FROM voyage_cache").fetchall())
    assert "Contenido" not in stored and "test-secret" not in stored


def test_rerank_index_mapping_and_cache(tmp_path):
    client = provider(tmp_path)
    pairs, usage = client.rerank("consulta", ["documento 1", "documento 2"], top_k=2)
    assert pairs == [(0, 1), (1, 0.5)]
    assert usage["tokens"] == 12
    assert (
        client.rerank("consulta", ["documento 1", "documento 2"], top_k=2)[1][
            "cache_hits"
        ]
        == 1
    )


@pytest.mark.parametrize("status", [401, 429, 500])
def test_errors_redact_provider_body_and_do_not_retry(tmp_path, status):
    calls = []

    def fail(request):
        calls.append(request)
        return httpx.Response(status, text="private payload test-secret-never-log")

    client = provider(tmp_path, fail, daily_requests=1)
    with pytest.raises(VoyageError) as error:
        client.embed([["documento"]])
    assert "private" not in str(error.value) and "test-secret" not in str(error.value)
    with pytest.raises(VoyageError, match="Cuota"):
        client.embed([["documento"]])
    assert len(calls) == 1 and client.usage()["reported_tokens"] == 0


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"data": [], "usage": {"total_tokens": 1}},
        {
            "data": [
                {"index": 0, "data": [{"index": 0, "embedding": [float("nan")] * 256}]}
            ],
            "usage": {"total_tokens": 1},
        },
        {
            "data": [{"index": 0, "data": [{"index": 0, "embedding": [1.0] * 255}]}],
            "usage": {"total_tokens": 1},
        },
    ],
)
def test_invalid_embeddings_are_not_cached(tmp_path, data):
    client = provider(tmp_path, lambda _: httpx.Response(200, json=data))
    with pytest.raises(VoyageError):
        client.embed([["documento"]])
    with sqlite3.connect(client.path) as db:
        assert db.execute("SELECT count(*) FROM voyage_cache").fetchone()[0] == 0


def test_invalid_rerank_index_fails_closed(tmp_path):
    client = provider(
        tmp_path,
        lambda _: httpx.Response(
            200,
            json={
                "data": [{"index": 8, "relevance_score": 1}],
                "usage": {"total_tokens": 1},
            },
        ),
    )
    with pytest.raises(VoyageError):
        client.rerank("q", ["doc"], top_k=1)


def test_persistent_request_and_token_quota(tmp_path):
    client = provider(tmp_path, daily_requests=1)
    client.embed([["doc"]])
    assert provider(tmp_path, daily_requests=1).embed([["doc"]])[1]["cache_hits"] == 1
    with pytest.raises(VoyageError, match="Cuota"):
        provider(tmp_path, daily_requests=1).embed([["nuevo"]])
    with pytest.raises(VoyageError, match="Cuota"):
        provider(tmp_path / "limited", daily_token_reservation=1).embed([["doc"]])


def test_concurrent_identical_requests_make_one_network_call(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return response_for(request)

    client = provider(tmp_path, handler)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: client.embed([["igual"]]), range(4)))
    assert len(calls) == 1
    assert sum(r[1]["requests"] for r in results) == 1


@pytest.mark.parametrize(
    "kwargs", [{"api_key": ""}, {"dimension": 100}, {"daily_requests": 0}]
)
def test_invalid_configuration(kwargs, tmp_path):
    with pytest.raises((ValueError, VoyageError)):
        VoyageProvider(**{"api_key": "test", "cache_path": tmp_path / "c.db", **kwargs})


class FakeClock:
    def __init__(self):
        self.now, self.waits = 1791689000.0, []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


def test_persistent_rpm_and_tpm_pacing_without_real_sleep(tmp_path):
    clock = FakeClock()
    options = dict(
        clock=clock,
        sleep=clock.sleep,
        requests_per_minute=1,
        token_bound_per_minute=200,
    )
    provider(tmp_path, **options).embed([["uno"]])
    provider(tmp_path, **options).embed([["dos"]])
    assert clock.waits == [61]
    # Caché ni espera ni consume quota.
    provider(tmp_path, **options).embed([["dos"]])
    assert clock.waits == [61]
    clock = FakeClock()
    options.update(clock=clock, sleep=clock.sleep, requests_per_minute=100)
    client = provider(tmp_path / "tpm", **options)
    client.embed([["a" * 50]])  # 114 bytes reservados; otro no cabe en 200/minuto.
    client.embed([["b" * 50]])
    assert clock.waits == [61]


def test_explicit_429_honors_retry_after_and_counts_each_attempt(tmp_path):
    clock, calls = FakeClock(), []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                429, headers={"Retry-After": "7"}, text="secret remote body"
            )
        return response_for(request)

    client = provider(
        tmp_path, handler, clock=clock, sleep=clock.sleep, max_429_retries=1
    )
    _, usage = client.embed([["doc"]])
    assert len(calls) == 2 and clock.waits == [7]
    assert usage["requests"] == 2 and client.usage()["requests"] == 2


def test_timeout_is_not_retried_and_long_cooldown_survives_restart(tmp_path):
    calls = []

    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout("private detail")

    with pytest.raises(VoyageError, match="no se reintentó"):
        provider(tmp_path, timeout, max_429_retries=3).embed([["doc"]])
    assert len(calls) == 1
    clock = FakeClock()
    limited = tmp_path / "limited"
    client = provider(
        limited,
        lambda _: httpx.Response(429, headers={"Retry-After": "500"}),
        clock=clock,
        sleep=clock.sleep,
        max_429_retries=1,
    )
    with pytest.raises(VoyageError, match="429"):
        client.embed([["doc"]])
    with pytest.raises(VoyageError, match="429"):
        provider(limited, clock=clock, sleep=clock.sleep).embed([["otro"]])
    assert clock.waits == []


def test_context_cache_reuses_unchanged_groups_and_batches_under_tpm(tmp_path):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return response_for(request)

    clock = FakeClock()
    client = provider(
        tmp_path, handler, token_bound_per_minute=150, clock=clock, sleep=clock.sleep
    )
    client.embed([["A"], ["B"]])
    result, usage = client.embed([["B"], ["C"]])
    assert len(result) == 2 and usage["cache_hits"] == 1
    assert calls[-1]["inputs"] == [["C"]]
    assert len(calls) == 2
    assert clock.waits == [61]
    with pytest.raises(ValueError, match="no se divide"):
        client.embed([["x" * 200]])


def test_cache_only_replays_without_key_network_or_writes(tmp_path):
    client = provider(tmp_path)
    groups = [["Documento"], ["Otro contexto"]]
    vectors = client.embed(groups)[0]
    query = client.embed([["consulta"]], input_type="query")[0]
    pairs = client.rerank("consulta", ["Documento", "Otro contexto"], top_k=2)[0]
    before, ledger = client.path.read_bytes(), client.usage()

    def forbidden(_):
        pytest.fail("cache-only no debe contactar red")

    cached = VoyageProvider(
        "",
        client.path,
        dimension=256,
        cache_only=True,
        token_bound_per_minute=1,
        transport=httpx.MockTransport(forbidden),
    )
    assert cached.embed(groups) == (
        vectors,
        {"requests": 0, "tokens": 0, "cache_hits": 2},
    )
    assert cached.embed([["consulta"]], input_type="query")[0] == query
    assert cached.rerank("consulta", ["Documento", "Otro contexto"], top_k=2)[0] == [
        list(p) for p in pairs
    ]
    with cached._db() as db, pytest.raises(sqlite3.OperationalError, match="readonly"):
        db.execute("DELETE FROM voyage_cache")
    assert cached.usage() == ledger and client.path.read_bytes() == before


@pytest.mark.parametrize("kind", ["embed", "query", "rerank"])
def test_cache_only_miss_is_explicit_and_does_not_spend_or_write(tmp_path, kind):
    client = provider(tmp_path)
    before, ledger = client.path.read_bytes(), client.usage()
    cached = VoyageProvider("", client.path, dimension=256, cache_only=True)
    with pytest.raises(VoyageCacheMiss) as error:
        if kind == "rerank":
            cached.rerank("consulta privada", ["documento privado"], top_k=1)
        else:
            cached.embed(
                [["documento privado"]],
                input_type="query" if kind == "query" else "document",
            )
    assert "privad" not in str(error.value)
    assert cached.usage() == ledger and client.path.read_bytes() == before


@pytest.mark.parametrize("kind", ["missing", "empty", "corrupt"])
def test_cache_only_rejects_missing_or_incompatible_database_without_initializing(
    tmp_path, kind
):
    path = tmp_path / "absent" / "cache.db"
    if kind != "missing":
        path.parent.mkdir()
        path.write_bytes(b"not sqlite" if kind == "corrupt" else b"")
    before = path.read_bytes() if path.exists() else None
    with pytest.raises(VoyageError, match="ausente o incompatible"):
        VoyageProvider("", path, cache_only=True)
    assert (path.read_bytes() if path.exists() else None) == before
    if kind == "missing":
        assert not path.parent.exists()
