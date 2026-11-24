"""El adaptador compartido no debe abrir conexiones nuevas por request.

Cada `get_database_adapter()` creaba un SurrealAdapter nuevo; con SurrealDB por
defecto eso abría dos websockets por request y ninguno se cerraba, hasta que el
event loop de Windows moría al liberar sockets pendientes (WinError 995 ->
InvalidStateError).
"""

import asyncio
import sys

from database import adapter as adapter_module
from database.redis_adapter import RedisAdapter

# `database.redis_adapter` es la instancia exportada por el paquete, no el módulo.
redis_module = sys.modules["database.redis_adapter"]


def test_default_adapter_is_shared_between_calls(monkeypatch):
    monkeypatch.setattr(adapter_module.settings, "DATABASE_BACKEND", "surrealdb")
    monkeypatch.setattr(adapter_module, "_default_adapters", {})

    first = adapter_module.get_database_adapter()
    second = adapter_module.get_database_adapter()

    assert first is second


def test_patched_postgres_factory_still_yields_fresh_instances(monkeypatch):
    monkeypatch.setattr(adapter_module.settings, "DATABASE_BACKEND", "surrealdb")
    monkeypatch.setattr(adapter_module, "_default_adapters", {})

    class FakePostgres:
        pass

    first = adapter_module.get_database_adapter(FakePostgres)
    second = adapter_module.get_database_adapter(FakePostgres)

    assert isinstance(first, FakePostgres)
    assert first is not second


def test_redis_initialize_is_idempotent(monkeypatch):
    adapter = RedisAdapter()
    created = []

    class FakeClient:
        async def ping(self):
            return True

        async def aclose(self):
            return None

    def fake_from_url(**kwargs):
        client = FakeClient()
        created.append(client)
        return client

    monkeypatch.setattr(redis_module.redis, "from_url", fake_from_url)

    async def run():
        await adapter.initialize()
        await adapter.initialize()
        await adapter.close()

    asyncio.run(run())

    assert len(created) == 1
    assert adapter.client is None


def test_redis_embedding_roundtrip_and_bounded_scan():
    class FakeClient:
        values = {}

        async def setex(self, key, ttl, value):
            self.values[key] = value
            return True

        async def get(self, key):
            return self.values.get(key)

        async def scan_iter(self, match):
            assert match == "embedding:*"
            for key in ("embedding:a", "embedding:a", "embedding:b", "embedding:c"):
                yield key

    async def run():
        adapter = RedisAdapter()
        adapter.client = FakeClient()
        assert await adapter.cache_embedding("a", [0.1, 0.2])
        assert await adapter.get_cached_embedding("a") == [0.1, 0.2]
        assert await adapter.get_cached_embedding("missing") is None
        assert await adapter.get_all_keys_pattern("embedding:*", 2) == ["embedding:a", "embedding:b"]
        assert await adapter.get_all_keys_pattern("embedding:*", 0) == []

    asyncio.run(run())
