"""Coincidencia de anclas y patrones del gold contra el texto de una respuesta.

Un patrón es una subcadena (comparada con ``compact``: sin tildes, mayúsculas,
espacios ni puntuación) o, con el prefijo ``re:``, una expresión regular sobre el
texto normalizado (minúsculas, sin tildes, espacios colapsados).
"""

import re

from utils.text_match import compact, normalize

REGEX_PREFIX = "re:"


def compile_pattern(pattern: str):
    return re.compile(pattern[len(REGEX_PREFIX):]) if pattern.startswith(REGEX_PREFIX) else None


def pattern_matches(text: str, pattern: str) -> bool:
    regex = compile_pattern(pattern)
    if regex is not None:
        return regex.search(normalize(text)) is not None
    needle = compact(pattern)
    return bool(needle) and needle in compact(text)


def anchor_matches(text: str, anchor: str) -> bool:
    return pattern_matches(text, anchor)


def anchors_satisfied(text: str, anchors) -> bool:
    """Todos los grupos deben tener al menos una alternativa presente en ``text``."""
    return all(any(anchor_matches(text, a) for a in group) for group in anchors)
