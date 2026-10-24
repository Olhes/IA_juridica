"""Abstención: recall de abstenciones exigidas y tasa de abstención innecesaria.

Se considera abstención tanto el estado formal del pipeline
(``evidence_status == "insufficient_evidence"``) como una no-respuesta explícita
en el texto (``Answer.abstained_semantic``); el estado formal se reporta aparte.
"""

from evaluation.harness.metrics.common import Score
from evaluation.harness.metrics.factuality import covered_facts


def abstention_recall(case, answer) -> Score:
    if not case.must_abstain:
        return Score.na("el caso no exige abstención")
    return Score.flag(answer.abstained)


def unnecessary_abstention(case, answer) -> Score:
    """Abstención en un caso respondible. Un aviso de límites dentro de una respuesta que
    sí cubre algún hecho no cuenta: solo una no-respuesta (o el estado formal)."""
    if case.must_abstain:
        return Score.na("el caso exige abstención")
    answered_something = any(covered_facts(case, answer.fact_text).values())
    return Score.flag(answer.abstained_formal or (answer.abstained_semantic and not answered_something))


def formal_abstention(case, answer) -> Score:
    if not case.must_abstain:
        return Score.na("el caso no exige abstención")
    return Score.flag(answer.abstained_formal)
