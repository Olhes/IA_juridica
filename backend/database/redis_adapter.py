"""Redis Adapter para IA Jurídica — cache y rate limiting."""

import asyncio
from contextlib import suppress
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional

import redis.asyncio as redis

from config.settings import settings

logger = logging.getLogger("ia_juridica.redis")


def _serialize_for_redis(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialize_for_redis(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize_for_redis(item) for item in obj]
    return obj


class RedisAdapter:
    """Adaptador asíncrono para Redis con soporte de cache y sesiones."""

    def __init__(self):
        self.client = None
        self._init_lock = asyncio.Lock()
        self.config = {
            "url": settings.REDIS_URL,
            "encoding": "utf-8",
            "decode_responses": True,
            "socket_connect_timeout": 5,
            "socket_timeout": 5,
            "retry_on_timeout": True,
        }

    async def initialize(self):
        """Publish the shared client only after its initial ping succeeds."""
        async with self._init_lock:
            if self.client is not None:
                return
            client = redis.from_url(**self.config)
            try:
                await client.ping()
            except BaseException:
                with suppress(Exception):
                    await client.aclose()
                raise
            self.client = client

    async def close(self):
        """Close the shared client and its pool."""
        async with self._init_lock:
            client, self.client = self.client, None
            if client is not None:
                await client.aclose()

    async def set_cache(self, key: str, value: Any, ttl: int = None) -> bool:
        try:
            ttl = ttl or settings.CACHE_TTL
            if isinstance(value, (dict, list)):
                value = json.dumps(_serialize_for_redis(value))
            return await self.client.setex(key, ttl, value)
        except Exception as error:
            logger.warning("redis_set_cache_failed error_type=%s", type(error).__name__)
            return False

    async def get_cache(self, key: str) -> Optional[Any]:
        try:
            value = await self.client.get(key)
            if not value:
                return None
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        except Exception as error:
            logger.warning("redis_get_cache_failed error_type=%s", type(error).__name__)
            return None

    async def delete_cache(self, key: str) -> bool:
        try:
            result = await self.client.delete(key)
            return result > 0
        except Exception as error:
            logger.warning("redis_delete_cache_failed error_type=%s", type(error).__name__)
            return False

    async def cache_embedding(
        self, text_hash: str, embedding: List[float], ttl: int = 86400
    ) -> bool:
        return await self.set_cache(
            f"embedding:{text_hash}", json.dumps(embedding), ttl
        )

    async def get_cached_embedding(self, text_hash: str) -> Optional[List[float]]:
        embedding = await self.get_cache(f"embedding:{text_hash}")
        # get_cache ya decodifica JSON; no intentar deserializar la lista dos veces.
        return embedding if isinstance(embedding, list) else None

    async def check_rate_limit(
        self, identifier: str, limit: int = 100, window_seconds: int = 900
    ) -> Dict[str, Any]:
        key = f"rate_limit:{identifier}"
        current_time = datetime.now(timezone.utc).timestamp()
        try:
            pipe = self.client.pipeline()
            pipe.zremrangebyscore(key, 0, current_time - window_seconds)
            pipe.zcard(key)
            pipe.zadd(key, {str(current_time): current_time})
            pipe.expire(key, window_seconds)
            results = await pipe.execute()
            current_requests = results[1]
            return {
                "allowed": current_requests < limit,
                "current": current_requests,
                "limit": limit,
                "remaining": max(0, limit - current_requests - 1),
                "reset_time": current_time + window_seconds,
            }
        except Exception as error:
            logger.warning("redis_rate_limit_failed error_type=%s", type(error).__name__)
            return {"allowed": True, "error": str(error)}

    async def health_check(self) -> Dict[str, Any]:
        try:
            start_time = datetime.now(timezone.utc)
            await self.client.ping()
            info = await self.client.info()
            return {
                "status": "healthy",
                "database": "redis",
                "version": info.get("redis_version", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "used_memory": info.get("used_memory_human", "unknown"),
                "response_time_ms": (
                    datetime.now(timezone.utc) - start_time
                ).total_seconds()
                * 1000,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception:
            return {
                "status": "unhealthy",
                "database": "redis",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    async def get_all_keys_pattern(self, pattern: str, limit: int = 100) -> List[str]:
        try:
            if limit <= 0:
                return []
            keys: List[str] = []
            seen = set()
            async for key in self.client.scan_iter(match=pattern):
                if key in seen:
                    continue
                seen.add(key)
                keys.append(key)
                if len(keys) >= limit:
                    break
            return keys
        except Exception as error:
            logger.warning("redis_scan_keys_failed error_type=%s", type(error).__name__)
            return []


redis_adapter = RedisAdapter()
