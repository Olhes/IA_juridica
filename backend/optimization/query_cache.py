"""Private, revision-aware answer cache. No implicit cross-user sharing."""

import hashlib
import json
from functools import cache

from config.settings import settings
from utils.pipeline_identity import pipeline_digest

PIPELINE_VERSION = "legal-answer-v2"


@cache
def _loaded_pipeline_digest():
    """La aplicación usa el código de este proceso; recalcular al reiniciar."""
    return pipeline_digest()


def answer_cache_key(
    query,
    language,
    owner_id,
    context=None,
    history=None,
    conversation_id=None,
    corpus_revision=None,
    mode="query",
):
    pipeline = _loaded_pipeline_digest()
    identity = {
        "pipeline": PIPELINE_VERSION,
        "prompt_digest": pipeline,
        "model": settings.COHERE_LLM_MODEL,
        "temperature": settings.COHERE_TEMPERATURE,
        "max_tokens": settings.COHERE_MAX_TOKENS,
        "query": query,
        "language": language,
        "owner": owner_id,
        "context": context or {},
        "history": history or [],
        "conversation": conversation_id,
        "corpus": corpus_revision,
        "mode": mode,
    }
    return hashlib.sha256(
        json.dumps(identity, sort_keys=True, ensure_ascii=False, default=str).encode(
            "utf-8"
        )
    ).hexdigest()
