"""Estimación de calidad (QE) de una traducción es→qu **sin referencia**.

Solo usa señales automáticas: ¿el resultado parece quechua?, ¿quedó español sin
traducir?, ¿se conservaron las referencias legales?, ¿la longitud es plausible?
``alta`` significa "pasa las comprobaciones automáticas", **no** que un hablante
nativo la haya revisado ni que sea jurídicamente exacta; por eso ``review_required``
sigue siendo verdadero siempre.
"""

import re

from modules.language.services.translation_service import REFERENCE_PATTERN
from utils.text_match import fold

BASIS = "Señales automáticas; no sustituyen la revisión de un hablante nativo."

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
COPY_RATE_SOFT, COPY_RATE_HARD = 0.4, 0.6
LENGTH_SOFT = (0.5, 1.8)
LENGTH_HARD = (0.3, 3.0)


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


def copy_rate(source: str, output: str) -> float:
    """Fracción de palabras (>= 4 letras) del resultado que ya estaban en el original."""
    source_words = set(tokens(source))
    words = [w for w in tokens(output) if len(w) >= 4]
    return sum(w in source_words for w in words) / len(words) if words else 0.0


def protected_spans(text: str) -> list:
    """Referencias que la traducción debe conservar tal cual (artículos, leyes, números, URL)."""
    return [m.group().strip() for m in re.finditer(REFERENCE_PATTERN, text, flags=re.I)]


def references_preserved(source: str, output: str) -> tuple:
    spans = protected_spans(source)
    folded = fold(output)
    missing = [s for s in spans if fold(s) not in folded]
    return len(spans) - len(missing), len(spans), missing


def length_ratio(source: str, output: str) -> float:
    return len(output.strip()) / max(len(source.strip()), 1)


def estimate_quality(source: str, output: str, *, success: bool = True) -> dict:
    """``{quality: alta|media|baja, signals, reasons, basis}``."""
    reasons_hard, reasons_soft = [], []
    kept, total, missing = references_preserved(source, output)
    ratio, copied = length_ratio(source, output), copy_rate(source, output)
    language = detect_language(output)
    if not success or not output.strip():
        reasons_hard.append("traducción no disponible")
    if language == "es":
        reasons_hard.append("el resultado parece español, no quechua")
    elif language == "unknown":
        reasons_soft.append("no se pudo confirmar que el resultado sea quechua")
    if missing:
        reasons_hard.append("se perdieron referencias legales")
    if copied > COPY_RATE_HARD:
        reasons_hard.append("gran parte del texto quedó sin traducir")
    elif copied > COPY_RATE_SOFT:
        reasons_soft.append("parte del texto parece sin traducir")
    if not LENGTH_HARD[0] <= ratio <= LENGTH_HARD[1]:
        reasons_hard.append("la longitud no es plausible")
    elif not LENGTH_SOFT[0] <= ratio <= LENGTH_SOFT[1]:
        reasons_soft.append("la longitud es inusual")
    quality = "baja" if reasons_hard else "media" if reasons_soft else "alta"
    return {
        "quality": quality,
        "reasons": reasons_hard + reasons_soft,
        "signals": {
            "language": language,
            "copy_rate": round(copied, 3),
            "length_ratio": round(ratio, 3),
            "references_kept": kept,
            "references_total": total,
        },
        "basis": BASIS,
    }
