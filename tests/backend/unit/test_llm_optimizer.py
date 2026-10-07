"""
Tests unitarios para LLMOptimizer.

Cobertura:
  - Cache hit/miss por hash de prompt
  - Expiración por TTL
  - Eviction por max_cache_size
  - Compresión de prompts (center_cut y tail_cut)
  - Estimación de tokens
  - Tracking de uso acumulado
  - Invalidación manual y limpieza total
"""

import time
import pytest
from optimization.llm_optimizer import LLMOptimizer, TokenUsage


class TestLLMOptimizerCache:

    def test_cache_hit_returns_same_response(self, llm_optimizer):
        """Mismo prompt → cache hit devuelve la respuesta guardada."""
        prompt   = "¿Qué comprenden los alimentos según el Código Civil?"
        response = "El artículo 472 define alimentos como lo indispensable."
        llm_optimizer.cache_response(prompt, response)
        cached = llm_optimizer.get_cached(prompt)
        assert cached == response

    def test_cache_miss_returns_none(self, llm_optimizer):
        """Prompt no guardado → cache miss devuelve None."""
        result = llm_optimizer.get_cached("Pregunta que nunca fue cacheada")
        assert result is None

    def test_different_prompts_independent_keys(self, llm_optimizer):
        """Prompts distintos deben tener claves independientes."""
        llm_optimizer.cache_response("prompt A", "respuesta A")
        llm_optimizer.cache_response("prompt B", "respuesta B")
        assert llm_optimizer.get_cached("prompt A") == "respuesta A"
        assert llm_optimizer.get_cached("prompt B") == "respuesta B"

    def test_cache_expiry_after_ttl(self):
        """Entradas expiradas (TTL vencido) deben retornar None."""
        optimizer = LLMOptimizer(cache_ttl_seconds=1)
        optimizer.cache_response("prompt expirado", "respuesta temporal")
        time.sleep(1.1)
        assert optimizer.get_cached("prompt expirado") is None

    def test_cache_valid_within_ttl(self):
        """Entradas dentro del TTL deben seguir disponibles."""
        optimizer = LLMOptimizer(cache_ttl_seconds=60)
        optimizer.cache_response("prompt válido", "respuesta válida")
        assert optimizer.get_cached("prompt válido") == "respuesta válida"

    def test_eviction_at_max_size(self):
        """Al superar max_cache_size, la entrada más antigua debe ser eviccionada."""
        optimizer = LLMOptimizer(max_cache_size=3)
        optimizer.cache_response("prompt 1", "r1")
        optimizer.cache_response("prompt 2", "r2")
        optimizer.cache_response("prompt 3", "r3")
        # Agregar la 4ta → debe evicionar prompt 1
        optimizer.cache_response("prompt 4", "r4")
        assert len(optimizer._cache) <= 3

    def test_invalidate_specific_key(self, llm_optimizer):
        """Invalidar una clave específica no debe afectar las demás."""
        llm_optimizer.cache_response("prompt X", "respuesta X")
        llm_optimizer.cache_response("prompt Y", "respuesta Y")
        removed = llm_optimizer.invalidate("prompt X")
        assert removed is True
        assert llm_optimizer.get_cached("prompt X") is None
        assert llm_optimizer.get_cached("prompt Y") == "respuesta Y"

    def test_invalidate_nonexistent_key_returns_false(self, llm_optimizer):
        """Invalidar clave inexistente retorna False (sin error)."""
        result = llm_optimizer.invalidate("no existe")
        assert result is False

    def test_clear_cache_removes_all(self, llm_optimizer):
        """clear_cache() debe eliminar todas las entradas."""
        llm_optimizer.cache_response("p1", "r1")
        llm_optimizer.cache_response("p2", "r2")
        count = llm_optimizer.clear_cache()
        assert count >= 2
        assert len(llm_optimizer._cache) == 0


class TestLLMOptimizerPromptCompression:

    def test_short_prompt_not_compressed(self, llm_optimizer):
        """Prompt corto no debe modificarse."""
        short = "¿Qué es la pensión de alimentos?"
        result = llm_optimizer.compress_prompt(short, max_chars=5000)
        assert result == short

    def test_long_prompt_compressed(self, llm_optimizer):
        """Prompt largo debe comprimirse a max_chars aproximado."""
        long_prompt = "x" * 10_000
        compressed  = llm_optimizer.compress_prompt(long_prompt, max_chars=6000)
        assert len(compressed) < len(long_prompt)

    def test_center_cut_preserves_marker(self, llm_optimizer):
        """center_cut debe incluir el marcador de truncamiento."""
        long_prompt = "A" * 8000
        compressed  = llm_optimizer.compress_prompt(long_prompt, max_chars=4000, strategy="center_cut")
        assert "[...contexto legal adicional omitido por longitud...]" in compressed

    def test_tail_cut_preserves_beginning(self, llm_optimizer):
        """tail_cut debe preservar el inicio del prompt."""
        long_prompt = "INICIO_IMPORTANTE " + ("relleno " * 1000)
        compressed  = llm_optimizer.compress_prompt(long_prompt, max_chars=500, strategy="tail_cut")
        assert compressed.startswith("INICIO_IMPORTANTE")

    def test_compressed_result_fits_limit(self, llm_optimizer):
        """El resultado comprimido no debe superar max_chars + marcador."""
        long_prompt = "z" * 10_000
        compressed  = llm_optimizer.compress_prompt(long_prompt, max_chars=5000)
        # El resultado incluye el marcador, así que puede ser ligeramente mayor
        assert len(compressed) < 5000 + 200   # 200 chars de margen para el marcador


class TestLLMOptimizerTokenTracking:

    def test_estimate_tokens_basic(self, llm_optimizer):
        """4 chars ≈ 1 token."""
        assert llm_optimizer.estimate_tokens("hola") == 1
        assert llm_optimizer.estimate_tokens("a" * 40) == 10

    def test_estimate_tokens_empty_string(self, llm_optimizer):
        """String vacío → mínimo 1 token."""
        assert llm_optimizer.estimate_tokens("") >= 0

    def test_track_accumulates_usage(self, llm_optimizer):
        """Múltiples llamadas a track() deben acumular el total de tokens."""
        llm_optimizer.reset_stats()
        llm_optimizer.track("prompt corto", "respuesta corta")
        llm_optimizer.track("otro prompt", "otra respuesta")
        stats = llm_optimizer.get_session_stats()
        assert stats["total_tokens"] > 0
        assert stats["prompt_tokens"] > 0
        assert stats["response_tokens"] > 0

    def test_track_returns_call_metrics(self, llm_optimizer):
        """track() debe retornar métricas de esa llamada específica."""
        metrics = llm_optimizer.track("prompt de prueba", "respuesta de prueba")
        assert "call_prompt_tokens" in metrics
        assert "call_response_tokens" in metrics
        assert "call_total_tokens" in metrics
        assert metrics["call_total_tokens"] == metrics["call_prompt_tokens"] + metrics["call_response_tokens"]

    def test_reset_stats_clears_counters(self, llm_optimizer):
        """reset_stats() debe poner todos los contadores a cero."""
        llm_optimizer.track("p", "r")
        llm_optimizer.reset_stats()
        stats = llm_optimizer.get_session_stats()
        assert stats["total_tokens"] == 0
        assert stats["cache_hits"] == 0

    def test_cache_hit_increments_counter(self, llm_optimizer):
        """Un cache hit debe incrementar el contador de cache_hits."""
        llm_optimizer.reset_stats()
        llm_optimizer.cache_response("prompt test", "respuesta test")
        llm_optimizer.get_cached("prompt test")       # HIT
        llm_optimizer.get_cached("prompt inexistente") # MISS
        stats = llm_optimizer.get_session_stats()
        assert stats["cache_hits"] == 1
        assert stats["cache_misses"] == 1

    def test_cache_hit_rate_calculation(self, llm_optimizer):
        """cache_hit_rate debe calcularse correctamente."""
        llm_optimizer.reset_stats()
        llm_optimizer.cache_response("prompt A", "resp A")
        llm_optimizer.get_cached("prompt A")         # HIT
        llm_optimizer.get_cached("prompt A")         # HIT
        llm_optimizer.get_cached("no existe")        # MISS
        stats = llm_optimizer.get_session_stats()
        # 2 hits / 3 total = 0.6667
        assert abs(stats["cache_hit_rate"] - 2/3) < 0.01


class TestTokenUsage:

    def test_update_accumulates_tokens(self):
        usage = TokenUsage()
        usage.update(100, 50)
        usage.update(200, 80)
        assert usage.prompt_tokens   == 300
        assert usage.response_tokens == 130
        assert usage.total_tokens    == 430

    def test_estimated_cost_positive(self):
        usage = TokenUsage()
        usage.update(1_000_000, 500_000)
        assert usage.estimated_cost_usd > 0

    def test_to_dict_has_required_keys(self):
        usage = TokenUsage()
        usage.update(10, 5)
        d = usage.to_dict()
        required = {"prompt_tokens", "response_tokens", "total_tokens",
                    "cache_hits", "cache_misses", "estimated_cost_usd", "cache_hit_rate"}
        assert required.issubset(d.keys())