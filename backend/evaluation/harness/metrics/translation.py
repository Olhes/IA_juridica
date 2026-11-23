"""SacreBLEU para es→qu, más señales de contrato que requieren reglas locales.

Ninguna de estas métricas sustituye la revisión de hablantes nativos.
"""

import math
import re
from itertools import zip_longest

from sacrebleu import __version__ as sacrebleu_version
from sacrebleu.metrics import BLEU, CHRF, TER

from evaluation.harness.metrics.common import Score
from services.translation_qe import copy_rate, detect_language, length_ratio, protected_spans
from utils.text_match import contains, fold
from utils.vectors import cosine

# Actualizar la revisión si cambian los parámetros, aunque no cambie la librería.
METRIC_PROTOCOL = f"sacrebleu-{sacrebleu_version}/v1"


def _metrics(*, sentence: bool):
    # El orden efectivo evita ceros artificiales en BLEU de textos muy cortos.
    # BLEU de corpus conserva la convención de cuatro órdenes (tokenizador 13a).
    return {
        "chrf++": CHRF(char_order=6, word_order=2, beta=2),
        "bleu": BLEU(tokenize="13a", smooth_method="exp", effective_order=sentence),
        "ter": TER(),
    }


def sentence_scores(hyp: str, refs) -> dict:
    values = {name: metric.sentence_score(hyp, refs).score / 100 for name, metric in _metrics(sentence=True).items()}
    return {name: Score(value, value, 1.0) for name, value in values.items()}


def corpus_scores(hypotheses: list[str], references_by_pair: list) -> dict:
    if not hypotheses:
        return {}
    # SacreBLEU recibe una columna por referencia; None indica que ese par no la tiene.
    references = [list(column) for column in zip_longest(*references_by_pair)]
    metrics = _metrics(sentence=False)
    values = {name: metric.corpus_score(hypotheses, references).score for name, metric in metrics.items()}
    return {**values, "n": len(hypotheses), "signatures": {name: str(metric.get_signature()) for name, metric in metrics.items()}}


def glossary_adherence(source: str, output: str, glossary) -> Score:
    """Términos del glosario presentes en el original cuya traducción de referencia aparece en el resultado."""
    folded = fold(source)
    applicable = [
        (term, alternatives)
        for term, alternatives in glossary
        if re.search(rf"(?<!\w){re.escape(fold(term))}(?!\w)", folded)
    ]
    if not applicable:
        return Score.na("el original no contiene términos del glosario")
    return Score.ratio(sum(any(contains(output, alt) for alt in alts) for _, alts in applicable), len(applicable))


def references_kept(source: str, output: str) -> Score:
    spans = protected_spans(source)
    if not spans:
        return Score.na("el original no contiene referencias que proteger")
    folded = fold(output)
    return Score.ratio(sum(fold(span) in folded for span in spans), len(spans))


def placeholder_leak(output: str) -> Score:
    return Score.flag("ZXQREF" in output.upper())


def language_ok(output: str) -> Score:
    return Score.flag(detect_language(output) == "qu")


def copy_score(source: str, output: str) -> Score:
    value = copy_rate(source, output)
    return Score(value, value, 1.0)


def coverage(refs, output: str) -> Score:
    """Longitud del resultado respecto de la referencia más cercana (1.0 = igual)."""
    if not output.strip():
        return Score(0.0, 0.0, 1.0)
    ratios = [length_ratio(ref, output) for ref in refs]
    value = min(ratios, key=lambda r: abs(math.log(r))) if all(r > 0 for r in ratios) else 0.0
    return Score(value, value, 1.0)


def round_trip(source: str, back_translation, embed) -> Score:
    """Similitud coseno entre el original y su retrotraducción (embeddings de ``embed``)."""
    if not back_translation or embed is None:
        return Score.na("sin retrotraducción o sin modelo de embeddings")
    vectors = embed([source, back_translation])
    value = cosine(vectors[0], vectors[1])
    return Score(value, value, 1.0)
