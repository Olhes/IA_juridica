"""Señales léxicas bilingües; `unknown` no equivale a español ni a quechua."""

import re

from utils.text_match import fold


SPANISH_STOPWORDS = frozenset(
    """a al algo ante antes como con contra cual cuando de del desde donde durante e el ella ellas ellos en entre es
    esa ese eso esta estas este esto estos fue ha han hay la las le les lo los mas me mi mis muy ni no nos o otra
    otro para pero por porque que quien se sin sobre son su sus te tu un una uno unos y ya yo""".split()
)
# Marcas casi exclusivas del quechua: k, w, q sin u, apóstrofo eyectivo, y sufijos frecuentes.
_QU_SUFFIXES = ("kuna", "paq", "manta", "chkan", "nchik", "yki", "yku", "sqa", "rqa", "pura", "masi", "niyuq", "yuq")
_QU_LETTERS = re.compile(r"[kw]|q(?!u)|['’]")
_TOKEN = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.UNICODE)

MIN_TOKENS = 4
SPANISH_RATIO_MAX = 0.2
QUECHUA_RATIO_MIN = 0.35


def tokens(text: str) -> list:
    return [t for t in _TOKEN.findall(fold(text))]


def language_signals(text: str) -> dict:
    words = tokens(text)
    if not words:
        return {"tokens": 0, "spanish_ratio": 0.0, "quechua_ratio": 0.0}
    spanish = sum(w in SPANISH_STOPWORDS for w in words)
    quechua = sum(
        1 for w in words if w not in SPANISH_STOPWORDS and (_QU_LETTERS.search(w) or w.endswith(_QU_SUFFIXES))
    )
    return {"tokens": len(words), "spanish_ratio": spanish / len(words), "quechua_ratio": quechua / len(words)}


def detect_language(text: str) -> str:
    """``qu`` | ``es`` | ``unknown`` con una heurística de funciones gramaticales y marcas quechuas."""
    signals = language_signals(text)
    if signals["tokens"] < MIN_TOKENS:
        return "unknown"
    if signals["spanish_ratio"] <= SPANISH_RATIO_MAX and signals["quechua_ratio"] >= QUECHUA_RATIO_MIN:
        return "qu"
    if signals["spanish_ratio"] > SPANISH_RATIO_MAX and signals["quechua_ratio"] < QUECHUA_RATIO_MIN:
        return "es"
    return "unknown"
