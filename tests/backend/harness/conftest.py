"""Fixtures del harness: corpus y gold reales, y respuestas sintéticas para las métricas."""

import pytest

from evaluation.harness.answers import Answer
from evaluation.harness.corpus import Corpus
from evaluation.harness.gold import load_gold


@pytest.fixture(scope="session")
def corpus():
    return Corpus.load()


@pytest.fixture(scope="session")
def gold(corpus):
    return load_gold(corpus=corpus)


@pytest.fixture(scope="session")
def cases(gold):
    return {case.id: case for case in gold}


ABSTENTION_TEXT = "No hay evidencia suficiente en el corpus para responder esta consulta."


def oracle_answer(case, **overrides) -> Answer:
    """Respuesta sintética ideal: repite los hechos exigidos o se abstiene."""
    if case.must_abstain:
        base = dict(text=ABSTENTION_TEXT, evidence_status="insufficient_evidence", confidence_score=0.2)
    else:
        text = " ".join(fact.text for fact in case.required_facts)
        base = dict(text=text, evidence_status="retrieved", confidence_score=0.9, sources=["fixture"])
    base.update(overrides)
    return Answer(**base)
