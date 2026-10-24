"""Precisión de citas, determinista: Ley / artículo / Casación contra el corpus.

``citation_in_corpus`` detecta números de norma inexistentes en el corpus;
``citation_acceptable`` exige además que la cita esté entre las aceptables del
caso (``acceptable_citations``). Ninguna comprueba que la norma diga lo que la
respuesta le atribuye ni su vigencia.
"""

from evaluation.harness.metrics.common import Score
from services.citation_verifier import citation_matches, despace, evidence_keys, extract_citations
from utils.text_match import compact


class CorpusIndex:
    """Claves de cita y texto compacto del corpus, para verificar sin recorrerlo cada vez."""

    def __init__(self, corpus):
        self.keys = set()
        parts = []
        for segment in corpus.segments.values():
            self.keys |= evidence_keys(segment.text)
            parts.append(segment.text)
        self.compact = compact(" ".join(parts))
        self.despaced = compact(despace(" ".join(parts)))

    def contains(self, citation) -> bool:
        if any(citation_matches(citation.key, key) for key in self.keys):
            return True
        if citation.kind in {"ley", "casacion", "decreto_supremo"}:
            digits = compact(citation.key.split(":", 1)[1])
            return digits in self.compact or digits in self.despaced
        return False


def cited(text):
    return extract_citations(text)


def citation_in_corpus(text, index: CorpusIndex) -> Score:
    citations = cited(text)
    if not citations:
        return Score.na("la respuesta no cita normas")
    return Score.ratio(sum(index.contains(c) for c in citations), len(citations))


def citation_acceptable(case, text) -> Score:
    if not case.acceptable_citations:
        return Score.na("el caso no define citas aceptables")
    citations = cited(text)
    if not citations:
        return Score.na("la respuesta no cita normas")
    ok = sum(
        any(citation_matches(c.key, a) or citation_matches(a, c.key) for a in case.acceptable_citations)
        for c in citations
    )
    return Score.ratio(ok, len(citations))


def citation_grounded(answer) -> Score:
    """Precisión contra la evidencia recuperada (``metadata.citations`` del runtime)."""
    if answer.citations is None:
        return Score.na("el pipeline no reporta citas verificadas")
    if not answer.citations:
        return Score.na("la respuesta no cita normas")
    return Score.ratio(sum(c.get("status") == "verified" for c in answer.citations), len(answer.citations))
