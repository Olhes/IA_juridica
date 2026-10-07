"""Private, revision-aware answer cache. No implicit cross-user sharing."""

import hashlib
import json
from pathlib import Path

from config.settings import settings

PIPELINE_VERSION = "legal-answer-v2"


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
    root = Path(__file__).resolve().parents[1]
    directories = (
        "services",
        "context",
        "agents",
        "modules/validation",
        "modules/language",
        "modules/rag",
    )
    prompt_files = sorted(
        p for directory in directories for p in (root / directory).rglob("*.py")
    )
    pipeline = hashlib.sha256(
        b"".join(p.read_bytes() for p in prompt_files)
    ).hexdigest()
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
