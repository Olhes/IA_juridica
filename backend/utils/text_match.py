"""Normalización de texto compartida por el gold, las métricas y el verificador.

El corpus contiene PDFs con OCR "espaciado" (``l a v i o l e n c i a``). La
comparación por contenido usa ``compact``: minúsculas, sin tildes y solo
caracteres alfanuméricos, de modo que el espaciado del OCR no impide encontrar
una cita textual.
"""

import re
import unicodedata

_WS = re.compile(r"\s+")


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def fold(text: str) -> str:
    """Minúsculas y sin tildes conservando la longitud (permite mapear posiciones al original)."""
    return "".join(
        (unicodedata.normalize("NFD", c)[0] if unicodedata.normalize("NFD", c) else c).lower()
        for c in text
    )


def normalize(text: str) -> str:
    """Minúsculas, sin tildes y con espacios colapsados (conserva los límites de palabra)."""
    return _WS.sub(" ", strip_accents(text).lower()).strip()


def compact(text: str) -> str:
    """Solo letras y dígitos en minúsculas y sin tildes; ignora espaciado y puntuación."""
    return "".join(c for c in strip_accents(text).lower() if c.isalnum())


def contains(haystack: str, needle: str) -> bool:
    """``needle`` aparece en ``haystack`` según ``compact``; un ``needle`` vacío no cuenta."""
    target = compact(needle)
    return bool(target) and target in compact(haystack)


def spaced_ocr_ratio(text: str) -> float:
    """Fracción de tokens que son una sola letra: síntoma de OCR espaciado."""
    tokens = text.split()
    if not tokens:
        return 0.0
    return sum(1 for t in tokens if len(t) == 1 and t.isalpha()) / len(tokens)
