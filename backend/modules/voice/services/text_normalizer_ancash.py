"""
Normalización de texto para TTS quechua ancashino (Fase 1).

Espeja voice-service/app.py::normalize_ancash para que la clave de caché
del backend sea canónica: el mismo texto con distinta puntuación/mayúsculas
pega en el mismo audio cacheado.
"""

import hashlib
import json
import re
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[3]
LEXICON_PATH = BACKEND_DIR / "docs" / "voice" / "ancash_lexicon.json"

_lex_cache: dict | None = None
_lex_path_loaded: Path | None = None


def normalize_ancash(text: str) -> str:
    """Minúsculas, sin puntuación (MMS-TTS entrena así), espacios colapsados."""
    t = text.lower().strip()
    t = re.sub(r"[^\w\s'ñáéíóúüâêîôûç\-]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def voice_cache_key(text: str, lang: str, voice: str) -> str:
    """Clave Redis estable: tts:<sha256(texto_normalizado|lang|voz)>."""
    canonical = f"{normalize_ancash(text)}|{lang}|{voice}"
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"tts:{digest}"


def load_lexicon(path: Path | None = None) -> dict | None:
    """Carga ancash_lexicon.json (lazy, cacheado). None si falta o es inválido."""
    global _lex_cache, _lex_path_loaded
    target = Path(path) if path else LEXICON_PATH
    if _lex_cache is not None and _lex_path_loaded == target:
        return _lex_cache
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        entries = data.get("entries", [])
    except (OSError, ValueError):
        return None
    index = {normalize_ancash(e["qu"]): e for e in entries if e.get("qu")}
    _lex_cache = {"entries": entries, "by_qu": index, "meta": data.get("meta", {})}
    _lex_path_loaded = target
    return _lex_cache


def canonical_form(text: str, lex: dict | None = None) -> str:
    """Si el texto coincide (normalizado) con una oración del corpus, devuelve
    la grafía canónica del corpus; si no, el texto intacto (sin léxico = no-op)."""
    lex = lex if lex is not None else load_lexicon()
    if not lex:
        return text
    hit = lex["by_qu"].get(normalize_ancash(text))
    return hit["qu"] if hit else text


def gloss_hint(text: str, limit: int = 5, lex: dict | None = None) -> list[dict]:
    """Hook para RAG/traducción: glosas {qu, es, variedad} del léxico.

    1) coincidencia exacta normalizada; 2) si no, subcadenas (input ≥4 chars).
    Pensado para `translation_service` (diccionario antes que Google Translate).
    """
    lex = lex if lex is not None else load_lexicon()
    if not lex:
        return []
    norm = normalize_ancash(text)
    if not norm:
        return []
    exact = lex["by_qu"].get(norm)
    if exact:
        e = exact
        return [{"qu": e["qu"], "es": e["es"], "variedad": e["variedad"]}]
    if len(norm) < 4:
        return []
    return [
        {"qu": e["qu"], "es": e["es"], "variedad": e["variedad"]}
        for e in lex["entries"]
        if norm in normalize_ancash(e["qu"])
    ][:limit]
