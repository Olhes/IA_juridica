"""
LLM Optimizer para IA Jurídica.

Proporciona:
  - Caché semántico de respuestas (TTL configurable, usando hash SHA-256)
  - Compresión de prompt (preserva inicio + fin del contexto RAG)
  - Estimación y tracking de tokens por sesión
  - Métricas de uso para monitoreo

Se usa como wrapper alrededor de las llamadas Cohere en el LegalAgent.
No remplaza el cliente Cohere — es una capa de optimización encima.

Uso:
    optimizer = LLMOptimizer()

    # En el agente:
    cached = optimizer.get_cached(prompt)
    if cached:
        return cached

    response = await cohere_client.chat(...)
    optimizer.cache_response(prompt, response.text)
    optimizer.track(prompt, response.text)
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from loguru import logger


@dataclass
class TokenUsage:
    """Registro de uso de tokens para una llamada o sesión."""

    prompt_tokens: int = 0
    response_tokens: int = 0
    total_tokens: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    estimated_cost_usd: float = 0.0

    # Cohere command-r7b-12-2024 pricing aproximado (USD por 1M tokens)
    _INPUT_COST_PER_M: float = field(default=0.075, repr=False, compare=False)
    _OUTPUT_COST_PER_M: float = field(default=0.300, repr=False, compare=False)

    def update(self, prompt_tokens: int, response_tokens: int) -> None:
        self.prompt_tokens += prompt_tokens
        self.response_tokens += response_tokens
        self.total_tokens += prompt_tokens + response_tokens
        self.estimated_cost_usd += (
            prompt_tokens / 1_000_000
        ) * self._INPUT_COST_PER_M + (
            response_tokens / 1_000_000
        ) * self._OUTPUT_COST_PER_M

    def to_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "response_tokens": self.response_tokens,
            "total_tokens": self.total_tokens,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            "cache_hit_rate": round(
                self.cache_hits / max(self.cache_hits + self.cache_misses, 1), 4
            ),
        }


# Tipo del caché interno: key → (response_payload, timestamp)
_CacheEntry = Tuple[Any, float]


class LLMOptimizer:
    """
    Capa de optimización LLM basada en caché SHA-256 + métricas de tokens.

    El caché es in-process (dict en memoria). Para producción multi-instancia
    se puede reemplazar el backend por Redis; la interfaz es idéntica.

    Args:
        cache_ttl_seconds:  TTL de entradas cacheadas (default: 3600 = 1 hora)
        max_cache_size:     Máximo de entradas en caché (LRU simple)
        chars_per_token:    Factor de estimación de tokens (default: 4)
    """

    def __init__(
        self,
        cache_ttl_seconds: int = 3600,
        max_cache_size: int = 500,
        chars_per_token: int = 4,
    ):
        self.ttl = cache_ttl_seconds
        self.max_cache_size = max_cache_size
        self.chars_per_token = chars_per_token

        self._cache: Dict[str, _CacheEntry] = {}
        self._usage = TokenUsage()

        logger.info(
            f"LLMOptimizer inicializado (ttl={cache_ttl_seconds}s, "
            f"max_cache={max_cache_size})"
        )

    # ── Caché ──────────────────────────────────────────────────────────────────

    def get_cached(self, prompt: str) -> Optional[Any]:
        """
        Busca una respuesta cacheada para el prompt dado.

        Returns:
            Payload cacheado si hay cache hit válido, None si no.
        """
        key = self._hash(prompt)
        entry = self._cache.get(key)
        if entry is None:
            self._usage.cache_misses += 1
            return None

        response_text, timestamp = entry
        if (time.time() - timestamp) > self.ttl:
            del self._cache[key]
            self._usage.cache_misses += 1
            logger.debug("Cache MISS (expired)")
            return None

        self._usage.cache_hits += 1
        logger.debug("Cache HIT")
        return response_text

    def cache_response(self, prompt: str, response: Any) -> None:
        """Almacena una respuesta en caché."""
        if len(self._cache) >= self.max_cache_size:
            self._evict_oldest()

        key = self._hash(prompt)
        self._cache[key] = (response, time.time())
        logger.debug(
            f"Respuesta cacheada (key={key[:8]}..., cache_size={len(self._cache)})"
        )

    def invalidate(self, prompt: str) -> bool:
        """Elimina una entrada específica del caché."""
        key = self._hash(prompt)
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear_cache(self) -> int:
        """Limpia todo el caché. Retorna el número de entradas eliminadas."""
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"Caché limpiado ({count} entradas eliminadas)")
        return count

    # ── Optimización de prompts ────────────────────────────────────────────────

    def compress_prompt(
        self,
        prompt: str,
        max_chars: int = 5000,
        strategy: str = "center_cut",
    ) -> str:
        """
        Comprime un prompt largo preservando la información más relevante.

        Estrategias:
          - "center_cut": preserva inicio + fin (los más densos en info legal)
          - "tail_cut":   trunca solo el final (preserva instrucciones al inicio)

        Args:
            prompt:    Prompt completo a comprimir
            max_chars: Límite máximo en caracteres
            strategy:  "center_cut" | "tail_cut"

        Returns:
            Prompt comprimido (o el original si ya cabe)
        """
        if len(prompt) <= max_chars:
            return prompt

        if strategy == "center_cut":
            half = max_chars // 2
            compressed = (
                prompt[:half]
                + "\n\n[...contexto legal adicional omitido por longitud...]\n\n"
                + prompt[-half:]
            )
        else:  # tail_cut
            compressed = prompt[:max_chars] + "\n[...truncado]"

        logger.debug(
            f"Prompt comprimido: {len(prompt)} → {len(compressed)} chars "
            f"(strategy={strategy})"
        )
        return compressed

    def estimate_tokens(self, text: str) -> int:
        """Estimación rápida de tokens (sin API). ~4 chars/token (GPT-style)."""
        return max(1, len(text) // self.chars_per_token)

    # ── Tracking de uso ────────────────────────────────────────────────────────

    def track(self, prompt: str, response: str) -> dict:
        """
        Registra el uso de tokens de una llamada LLM y retorna las métricas.

        Returns:
            Dict con tokens de esta llamada y totales de sesión.
        """
        p_tokens = self.estimate_tokens(prompt)
        r_tokens = self.estimate_tokens(response)
        self._usage.update(p_tokens, r_tokens)

        call_metrics = {
            "call_prompt_tokens": p_tokens,
            "call_response_tokens": r_tokens,
            "call_total_tokens": p_tokens + r_tokens,
        }
        logger.debug(f"Token usage tracked: {call_metrics}")
        return call_metrics

    def get_session_stats(self) -> dict:
        """Retorna las métricas acumuladas de la sesión."""
        return self._usage.to_dict()

    def reset_stats(self) -> None:
        """Reinicia el contador de métricas (no limpia el caché)."""
        self._usage = TokenUsage()
        logger.info("Estadísticas de sesión reiniciadas")

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _hash(text: str) -> str:
        """SHA-256 del prompt como llave de caché."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _evict_oldest(self) -> None:
        """Elimina la entrada más antigua del caché (política FIFO simple)."""
        if not self._cache:
            return
        oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
        del self._cache[oldest_key]
        logger.debug(f"Caché: entrada antigua evicted (key={oldest_key[:8]}...)")
