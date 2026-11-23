"""Pipeline experimental de evaluación: recuperación Voyage y generación NVIDIA.

No modifica el pipeline de producción. Solo envía fragmentos candidatos del corpus,
nunca los hechos esperados ni las respuestas gold, a los proveedores externos.
"""

import asyncio
import os
import re

import httpx

from evaluation.harness.answers import Answer
from retrieval.voyage import VoyageError, VoyageProvider, VoyageRateLimit
from utils.vectors import cosine_scores

MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
URL = "https://integrate.api.nvidia.com/v1/chat/completions"


async def ragas_string_similarity(cases, answers):
    """Similitud textual con hechos de referencia; no mide exactitud semántica."""
    try:
        from ragas.metrics.collections import NonLLMStringSimilarity
    except ImportError:
        return {"available": False, "reason": "ragas no instalado", "value": None, "n": 0}
    scorer = NonLLMStringSimilarity()
    references = {case.id: " ".join(f.text for f in case.required_facts) for case in cases}
    values = []
    for entry in answers:
        reference = references.get(entry["case_id"], "")
        response = entry["answer"].get("text_es") or entry["answer"].get("text") or ""
        if reference and response:
            result = await scorer.ascore(reference=reference, response=response)
            values.append(float(result.value))
    return {"available": True, "value": sum(values) / len(values) if values else None, "n": len(values)}


def build_answer_fn(corpus, cache_path, *, delay_seconds=0):
    from config.settings import settings

    key = os.getenv("NVIDIA_API_KEY", "").strip()
    voyage_key = settings.VOYAGE_API_KEY.get_secret_value()
    if not key or not voyage_key:
        raise ValueError("Se requieren NVIDIA_API_KEY y VOYAGE_API_KEY")
    provider = VoyageProvider(voyage_key, cache_path, dimension=settings.VOYAGE_DIMENSION,
                              daily_requests=settings.VOYAGE_DAILY_REQUESTS,
                              daily_token_reservation=settings.VOYAGE_DAILY_TOKEN_RESERVATION,
                              requests_per_minute=settings.VOYAGE_REQUESTS_PER_MINUTE,
                              token_bound_per_minute=settings.VOYAGE_TOKEN_BOUND_PER_MINUTE,
                              max_429_retries=0)
    client = httpx.AsyncClient(timeout=90.0)
    segments = sorted(corpus.segments.values(), key=lambda s: s.id)
    previous_request = False
    quota_exhausted = False

    async def answer(case, sample):
        nonlocal previous_request, quota_exhausted
        del sample
        if quota_exhausted:
            raise VoyageError("Cuota local Voyage agotada")
        if previous_request and delay_seconds:
            await asyncio.sleep(delay_seconds)
        previous_request = True
        terms = set(re.findall(r"\w{3,}", case.query.lower()))
        candidates = sorted(segments, key=lambda s: (-len(terms.intersection(re.findall(r"\w{3,}", s.text.lower()))), s.id))[:8]
        if not candidates:
            raise ValueError("Corpus sin segmentos")
        docs = [s.text[:1200] for s in candidates]
        try:
            query_vectors, _ = await asyncio.to_thread(provider.embed, [[case.query]], input_type="query")
            doc_vectors, _ = await asyncio.to_thread(provider.embed, [[d] for d in docs], input_type="document")
            scores = cosine_scores([item for item, in doc_vectors], query_vectors[0][0])
            ranked = sorted(range(len(docs)), key=lambda i: (-scores[i], i))[:5]
            reranked, _ = await asyncio.to_thread(provider.rerank, case.query, [docs[i] for i in ranked], top_k=len(ranked))
        except VoyageError as error:
            if isinstance(error, VoyageRateLimit) or str(error).startswith("Cuota local Voyage agotada"):
                quota_exhausted = True
            raise
        selected = [ranked[i] for i, _ in reranked[:3]]
        contexts = [docs[i] for i in selected]
        prompt = "Responde solo con la evidencia; si no basta, indica que no hay evidencia suficiente.\n\nEvidencia:\n" + "\n\n".join(contexts) + "\n\nPregunta: " + case.query
        response = await client.post(URL, headers={"Authorization": f"Bearer {key}"}, json={
            "model": MODEL, "messages": [{"role": "user", "content": prompt}],
            "temperature": 0, "max_tokens": 1024,
            "chat_template_kwargs": {"enable_thinking": False},
        })
        response.raise_for_status()
        text = response.json()["choices"][0]["message"].get("content")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("NVIDIA devolvió una respuesta vacía")
        return Answer(text=text, contexts=contexts, sources=[candidates[i].doc_id for i in selected])

    answer.close = client.aclose
    return answer
