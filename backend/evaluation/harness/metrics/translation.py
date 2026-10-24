"""Métricas de traducción es→qu: chrF++ (principal), BLEU, TER sin desplazamientos y señales de contrato.

chrF++, BLEU y TER son implementaciones propias (sin dependencias) que siguen las
definiciones publicadas; sus decimales pueden diferir de sacrebleu. Con varias
referencias se toma la mejor por par. Ninguna mide si la traducción es *adecuada*
para un hablante: eso lo decide la revisión nativa.
"""

import math
import re
from collections import Counter

from evaluation.harness.metrics.common import Score
from services.translation_qe import copy_rate, detect_language, length_ratio, protected_spans
from utils.text_match import contains, fold

CHAR_ORDER, WORD_ORDER, BETA = 6, 2, 2
_WORD = re.compile(r"\w+(?:['’]\w+)*|[^\w\s]", re.UNICODE)


def words(text: str) -> list:
    return _WORD.findall(text)


def _ngrams(items, n):
    return Counter(tuple(items[i : i + n]) for i in range(len(items) - n + 1)) if len(items) >= n else Counter()


def chrf_stats(hyp: str, ref: str, char_order=CHAR_ORDER, word_order=WORD_ORDER) -> list:
    """``[(coincidencias, total_hip, total_ref)]`` por orden: caracteres 1..6 y palabras 1..2."""
    h_chars, r_chars = list(re.sub(r"\s+", "", hyp)), list(re.sub(r"\s+", "", ref))
    h_words, r_words = words(hyp), words(ref)
    stats = []
    for n in range(1, char_order + 1):
        h, r = _ngrams(h_chars, n), _ngrams(r_chars, n)
        stats.append((sum((h & r).values()), sum(h.values()), sum(r.values())))
    for n in range(1, word_order + 1):
        h, r = _ngrams(h_words, n), _ngrams(r_words, n)
        stats.append((sum((h & r).values()), sum(h.values()), sum(r.values())))
    return stats


def chrf_from_stats(stats, beta=BETA) -> float:
    precisions, recalls = [], []
    for match, h_total, r_total in stats:
        if h_total > 0 and r_total > 0:
            precisions.append(match / h_total)
            recalls.append(match / r_total)
    if not precisions:
        return 0.0
    p, r = sum(precisions) / len(precisions), sum(recalls) / len(recalls)
    if p + r == 0:
        return 0.0
    return 100.0 * (1 + beta**2) * p * r / (beta**2 * p + r)


def chrf(hyp: str, refs, **kwargs) -> float:
    """chrF++ (0–100) contra la mejor referencia."""
    return max(chrf_from_stats(chrf_stats(hyp, ref), **kwargs) for ref in refs)


def best_chrf_stats(hyp: str, refs) -> list:
    return max((chrf_stats(hyp, ref) for ref in refs), key=chrf_from_stats)


def bleu_stats(hyp: str, ref: str, max_order=4) -> dict:
    h, r = words(hyp), words(ref)
    matches, totals = [], []
    for n in range(1, max_order + 1):
        hn, rn = _ngrams(h, n), _ngrams(r, n)
        matches.append(sum((hn & rn).values()))
        totals.append(max(len(h) - n + 1, 0))
    return {"matches": matches, "totals": totals, "hyp_len": len(h), "ref_len": len(r)}


def bleu_from_stats(stats: dict, smooth=True) -> float:
    if stats["hyp_len"] == 0:
        return 0.0
    log_sum, smooth_value = 0.0, 1.0
    for match, total in zip(stats["matches"], stats["totals"]):
        if total == 0:
            return 0.0
        if match == 0:
            if not smooth:
                return 0.0
            smooth_value *= 2
            precision = 1.0 / (smooth_value * total)
        else:
            precision = match / total
        log_sum += math.log(precision)
    ratio = stats["hyp_len"] / stats["ref_len"] if stats["ref_len"] else 0.0
    brevity = 1.0 if ratio >= 1 else math.exp(1 - 1 / ratio) if ratio > 0 else 0.0
    return 100.0 * brevity * math.exp(log_sum / len(stats["matches"]))


def best_bleu_stats(hyp: str, refs) -> dict:
    return max((bleu_stats(hyp, ref) for ref in refs), key=bleu_from_stats)


def merge_bleu_stats(all_stats) -> dict:
    return {
        "matches": [sum(s["matches"][i] for s in all_stats) for i in range(4)],
        "totals": [sum(s["totals"][i] for s in all_stats) for i in range(4)],
        "hyp_len": sum(s["hyp_len"] for s in all_stats),
        "ref_len": sum(s["ref_len"] for s in all_stats),
    }


def ter(hyp: str, refs) -> float:
    """TER sin desplazamientos: distancia de edición de palabras / palabras de la referencia (cota superior)."""
    h = [w.lower() for w in words(hyp)]
    best = None
    for ref in refs:
        r = [w.lower() for w in words(ref)]
        if not r:
            continue
        previous = list(range(len(r) + 1))
        for i, hw in enumerate(h, 1):
            current = [i]
            for j, rw in enumerate(r, 1):
                current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (hw != rw)))
            previous = current
        rate = 100.0 * previous[-1] / len(r)
        best = rate if best is None else min(best, rate)
    return best if best is not None else 0.0


def sentence_scores(hyp: str, refs) -> dict:
    chrf_value = chrf(hyp, refs) / 100
    bleu_value = bleu_from_stats(best_bleu_stats(hyp, refs)) / 100
    ter_value = ter(hyp, refs) / 100
    return {
        "chrf++": Score(chrf_value, chrf_value, 1.0),
        "bleu": Score(bleu_value, bleu_value, 1.0),
        "ter": Score(ter_value, ter_value, 1.0),
    }


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


def cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def round_trip(source: str, back_translation, embed) -> Score:
    """Similitud coseno entre el original y su retrotraducción (embeddings de ``embed``)."""
    if not back_translation or embed is None:
        return Score.na("sin retrotraducción o sin modelo de embeddings")
    vectors = embed([source, back_translation])
    value = cosine(vectors[0], vectors[1])
    return Score(value, value, 1.0)
