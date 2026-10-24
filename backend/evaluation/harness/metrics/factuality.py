"""Legal factuality: recall de hechos exigidos y afirmaciones prohibidas.

La cobertura de un hecho es **léxica** (anclas del gold) y por tanto una
cota conservadora; el juez, si está disponible, aporta una segunda lectura
(``fact_recall_judge``). Una afirmación prohibida detectada por patrón es un
*candidato*: los patrones son heurísticos y un abogado decide.
"""

from evaluation.harness.matching import anchors_satisfied, pattern_matches
from evaluation.harness.metrics.common import Score


def covered_facts(case, text) -> dict:
    return {fact.id: anchors_satisfied(text, fact.anchors) for fact in case.required_facts}


def forbidden_hits(case, text) -> list:
    return [c.id for c in case.forbidden_claims if any(pattern_matches(text, p) for p in c.patterns)]


def fact_recall(case, text) -> Score:
    if case.must_abstain or not case.required_facts:
        return Score.na("el caso no exige hechos")
    hits = covered_facts(case, text)
    return Score.ratio(sum(hits.values()), len(hits))


def forbidden_claim(case, text) -> Score:
    """1.0 si la respuesta afirma algo prohibido (peor); ``n/a`` si el caso no define ninguna."""
    if not case.forbidden_claims:
        return Score.na("el caso no define afirmaciones prohibidas")
    return Score.flag(bool(forbidden_hits(case, text)))


def legal_factuality(case, text) -> Score:
    """Recall de hechos, o 0 si hay una afirmación prohibida; ``n/a`` si no se exigen hechos."""
    recall = fact_recall(case, text)
    if not recall.applicable:
        return Score.na(recall.na_reason)
    if forbidden_hits(case, text):
        return Score(0.0, 0.0, 1.0)
    return Score(recall.value, recall.value, 1.0)


def factual_pass(case, text):
    """``True`` si cubre todos los hechos y no afirma nada prohibido; ``None`` si no aplica."""
    recall = fact_recall(case, text)
    if not recall.applicable:
        return None
    return recall.value == 1.0 and not forbidden_hits(case, text)
