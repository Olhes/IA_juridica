"""Métricas de recuperación a nivel de evidencia (definición del plan SAT) y de fragmento.

``G`` = segmentos relevantes del caso; ``R_k`` = IDs distintos de segmento devueltos
en los primeros ``k`` fragmentos (los fragmentos sin correspondencia cuentan como
IDs devueltos no relevantes). Denominador cero => ``n/a``.
"""

import math

from evaluation.harness.metrics.common import Score


def ids_at(ranked_ids, k):
    """IDs distintos de los primeros ``k`` fragmentos."""
    seen = []
    for ids in ranked_ids[:k]:
        for segment_id in ids:
            if segment_id not in seen:
                seen.append(segment_id)
    return seen


def evidence_recall(ranked_ids, relevant, k) -> Score:
    if not relevant:
        return Score.na("el caso no exige evidencia")
    return Score.ratio(len(set(ids_at(ranked_ids, k)) & set(relevant)), len(relevant))


def evidence_precision(ranked_ids, relevant, k) -> Score:
    returned = ids_at(ranked_ids, k)
    if not relevant:
        return Score.na("el caso no exige evidencia")
    if not returned:
        return Score.na("no se devolvió ningún fragmento")
    return Score.ratio(len(set(returned) & set(relevant)), len(returned))


def chunk_precision(ranked_ids, relevant, k) -> Score:
    chunks = ranked_ids[:k]
    if not relevant:
        return Score.na("el caso no exige evidencia")
    if not chunks:
        return Score.na("no se devolvió ningún fragmento")
    return Score.ratio(sum(bool(set(ids) & set(relevant)) for ids in chunks), len(chunks))


def mrr(ranked_ids, relevant) -> Score:
    if not relevant:
        return Score.na("el caso no exige evidencia")
    for rank, ids in enumerate(ranked_ids, 1):
        if set(ids) & set(relevant):
            return Score(1.0 / rank, 1.0 / rank, 1.0)
    return Score(0.0, 0.0, 1.0)


def ndcg(ranked_ids, relevant, k) -> Score:
    """nDCG@k con relevancia binaria por fragmento; el ideal supone un fragmento por segmento relevante."""
    if not relevant:
        return Score.na("el caso no exige evidencia")
    gains = [1.0 if set(ids) & set(relevant) else 0.0 for ids in ranked_ids[:k]]
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(relevant), k)))
    return Score(dcg / ideal, dcg / ideal, 1.0)


def jurisprudence_hit(ranked_ids, jurisprudence, k) -> Score:
    if not jurisprudence:
        return Score.na("el caso no involucra jurisprudencia")
    return Score.flag(bool(set(ids_at(ranked_ids, k)) & set(jurisprudence)))


def empty_result(n_chunks, relevant) -> Score:
    """1.0 si no se devolvió nada para un caso que exige evidencia (``no_match`` indebido)."""
    if not relevant:
        return Score.na("el caso no exige evidencia")
    return Score.flag(n_chunks == 0)


def empty_when_unanswerable(n_chunks, must_abstain) -> Score:
    """1.0 si no se devolvió nada para un caso fuera del corpus (lo deseable)."""
    if not must_abstain:
        return Score.na("el caso es respondible")
    return Score.flag(n_chunks == 0)


def fallback_used(method) -> Score:
    if method is None:
        return Score.na("el sistema no reporta método")
    return Score.flag(str(method).startswith("fallback"))


def threshold_loss(ranked_ids, scores, relevant, top_k, threshold) -> Score:
    """Evidencia relevante entre los ``top_k`` del reranker que el umbral mínimo descarta.

    ``ranked_ids``/``scores`` están en el orden del reranker (mayor puntuación primero).
    """
    if not relevant:
        return Score.na("el caso no exige evidencia")
    relevant_scored = [s for ids, s in zip(ranked_ids[:top_k], scores[:top_k]) if set(ids) & set(relevant)]
    if not relevant_scored:
        return Score.na("el reranker no puso evidencia relevante entre los primeros resultados")
    return Score.ratio(sum(s < threshold for s in relevant_scored), len(relevant_scored))
