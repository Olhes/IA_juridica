"""Evalúa por separado cada etapa de la recuperación de jurisprudencia.

Sistemas (``SYSTEMS``): LightRAG puro en sus modos ``naive``/``local``/``global``/
``hybrid``/``mix``; solo léxico (BM25 local); la mezcla actual antes del rerank; el
resultado tras el rerank con el umbral mínimo (``current_reranked``) y el mismo
rerank sin umbral (``reranked_no_threshold``) para medir su coste.

Los fragmentos se mapean a segmentos con la regla de ``overlap``. Los sistemas que
dependen de LightRAG o de Cohere solo existen con ``--run-model-evals`` (o desde un
cassette): si no están disponibles sus métricas son ``n/a`` con la razón.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from evaluation.harness.metrics import retrieval as m
from evaluation.harness.metrics.common import Score, aggregate, merge_samples

GRAPH_MODES = ("naive", "local", "global", "hybrid", "mix")
SYSTEMS = tuple(f"lightrag_{mode}" for mode in GRAPH_MODES) + (
    "lexical",
    "current_mix",
    "current_reranked",
    "reranked_no_threshold",
)
KS = (1, 3, 5, 10)
MAIN_K = 5
PER_K = ("evidence_recall", "evidence_precision", "chunk_precision", "ndcg", "jurisprudence_hit")
GLOBAL = ("mrr", "empty_when_answerable", "empty_when_unanswerable", "fallback", "threshold_loss")


@dataclass
class Retrieved:
    """Fragmentos de un sistema para una consulta, en orden de ranking."""

    chunks: list = field(default_factory=list)  # [{"content": str, "score": float|None}]
    method: Optional[str] = None
    unavailable: Optional[str] = None
    extra: dict = field(default_factory=dict)

    def to_json(self):
        return {"chunks": self.chunks, "method": self.method, "unavailable": self.unavailable, "extra": self.extra}

    @classmethod
    def from_json(cls, data):
        return cls(**data)


def _chunk(doc):
    return {"content": doc["content"], "score": doc.get("relevance_score")}


async def retrieve_bundle(engine, query, *, budget, top_k, systems=SYSTEMS) -> dict:
    """Ejecuta los sistemas pedidos contra ``engine`` (red solo si hay LightRAG/Cohere)."""
    import inspect

    from modules.rag.services import lightrag_engine as module

    out: dict = {}
    # Commits anteriores a F2 no exponen `_graph_docs` ni `trace`: esos sistemas quedan n/a con su razón.
    can_graph = hasattr(engine, "_graph_docs")
    can_trace = "trace" in inspect.signature(engine.query_with_rerank).parameters
    graph_ready = module.LIGHTRAG_AVAILABLE and engine.rag is not None and can_graph
    for system in systems:
        if system.startswith("lightrag_"):
            if not graph_ready:
                reason = "LightRAG no está inicializado" if can_graph else "este commit no expone `_graph_docs`"
                out[system] = Retrieved(unavailable=reason)
                continue
            docs = await engine._graph_docs(query, system.removeprefix("lightrag_"), budget)
            out[system] = Retrieved([_chunk(d) for d in docs], method="graph" if docs else "graph_empty")
        elif system == "lexical":
            out[system] = Retrieved([_chunk(d) for d in engine._local_candidates(query, budget)], method="bm25")
    if {"current_mix", "current_reranked", "reranked_no_threshold"} & set(systems):
        trace: dict = {}
        if can_trace:
            result = await engine.query_with_rerank(query, top_k=top_k, rerank_candidates=budget, trace=trace)
        else:
            result = await engine.query_with_rerank(query, top_k=top_k, rerank_candidates=budget)
        candidates = trace.get("candidates", [])
        method = result.get("method")
        if "current_mix" in systems:
            out["current_mix"] = (
                Retrieved([_chunk(d) for d in candidates], method="mix")
                if can_trace
                else Retrieved(unavailable="este commit no expone `trace`")
            )
        if "current_reranked" in systems:
            out["current_reranked"] = Retrieved(
                [_chunk(d) for d in result.get("documents", [])],
                method=method,
                extra={
                    "threshold": trace.get("threshold"),
                    "reranker": trace.get("reranker"),
                    "rerank": trace.get("rerank"),
                    "candidates": [c["content"] for c in candidates],
                    "top_k": top_k,
                },
            )
        if "reranked_no_threshold" in systems:
            ranked = trace.get("rerank")
            if ranked is None:
                out["reranked_no_threshold"] = Retrieved(unavailable="sin reranker de Cohere")
            else:
                out["reranked_no_threshold"] = Retrieved(
                    [{"content": candidates[i]["content"], "score": s} for i, s in ranked[:top_k]], method=method
                )
    return out


def _score_system(case, retrieved: Retrieved, matcher, ks, main_k):
    """``{metric: Score}`` y ``{metric@k: Score}`` de un sistema para un caso."""
    relevant = case.relevant
    if retrieved.unavailable:
        reason = f"sistema no disponible: {retrieved.unavailable}"
        scores = {f"{name}@{k}": Score.na(reason) for name in PER_K for k in ks}
        scores.update({name: Score.na(reason) for name in GLOBAL})
        return scores, []
    ranked = [matcher.ids(c["content"]) for c in retrieved.chunks]
    scores = {}
    for k in ks:
        scores[f"evidence_recall@{k}"] = m.evidence_recall(ranked, relevant, k)
        scores[f"evidence_precision@{k}"] = m.evidence_precision(ranked, relevant, k)
        scores[f"chunk_precision@{k}"] = m.chunk_precision(ranked, relevant, k)
        scores[f"ndcg@{k}"] = m.ndcg(ranked, relevant, k)
        scores[f"jurisprudence_hit@{k}"] = m.jurisprudence_hit(ranked, case.jurisprudence, k)
    scores["mrr"] = m.mrr(ranked, relevant)
    scores["empty_when_answerable"] = m.empty_result(len(retrieved.chunks), relevant)
    scores["empty_when_unanswerable"] = m.empty_when_unanswerable(len(retrieved.chunks), case.must_abstain)
    scores["fallback"] = m.fallback_used(retrieved.method)
    scores["threshold_loss"] = Score.na("solo aplica al sistema con rerank y umbral")
    extra = retrieved.extra
    if extra.get("rerank") and extra.get("candidates") is not None:
        order = extra["rerank"]
        candidate_ids = [matcher.ids(text) for text in extra["candidates"]]
        scores["threshold_loss"] = m.threshold_loss(
            [candidate_ids[i] for i, _ in order], [s for _, s in order], relevant, extra.get("top_k", main_k), extra["threshold"]
        )
    return scores, ranked


def evaluate_retrieval(cases, bundles, matcher, *, systems=SYSTEMS, ks=KS, main_k=MAIN_K) -> dict:
    """``bundles``: ``{case_id: {system: Retrieved}}`` (o varias muestras en una lista)."""
    per_case = defaultdict(dict)
    for case in cases:
        sample_list = bundles.get(case.id)
        if sample_list is None:
            continue
        samples = sample_list if isinstance(sample_list, list) else [sample_list]
        for system in systems:
            scored = [_score_system(case, s[system], matcher, ks, main_k)[0] for s in samples if system in s]
            if scored:
                per_case[system][case.id] = {name: merge_samples([sc[name] for sc in scored]) for name in scored[0]}
    by_id = {c.id: c for c in cases}

    def summarise(selector):
        summary = {}
        for system, rows in per_case.items():
            chosen = {cid: row for cid, row in rows.items() if selector(by_id[cid])}
            names = list(next(iter(rows.values())))
            summary[system] = {name: aggregate([row[name] for row in chosen.values()]) for name in names} if chosen else {}
        return summary

    main = {
        system: {name: agg for name, agg in metrics.items() if name.endswith(f"@{main_k}") or "@" not in name}
        for system, metrics in summarise(lambda c: True).items()
    }
    return {
        "suite": "retrieval",
        "ndcg_definition": "binary_unique_segments_tie_averaged_v1",
        "ks": list(ks),
        "main_k": main_k,
        "n_cases": len(cases),
        "systems": summarise(lambda c: True),
        "main": main,
        "by_stratum": {s: summarise(lambda c, s=s: c.stratum == s) for s in sorted({c.stratum for c in cases})},
        "by_split": {s: summarise(lambda c, s=s: c.split == s) for s in sorted({c.split for c in cases})},
        "cases": {
            system: {cid: {n: v.to_json() for n, v in row.items() if n.endswith(f"@{main_k}") or "@" not in n} for cid, row in rows.items()}
            for system, rows in per_case.items()
        },
    }


async def ragas_id_crosscheck(cases, bundles, matcher, *, system="current_reranked", k=MAIN_K) -> dict:
    """Control cruzado con RAGAS (``IDBasedContextRecall``/``Precision``, sin LLM).

    Los IDs recuperados son los segmentos del gold presentes en los ``k`` primeros fragmentos
    del sistema. El recall de RAGAS debe coincidir con ``evidence_recall@k``; la precisión de
    RAGAS cuenta segmentos, no fragmentos, y se reporta aparte. Sin RAGAS instalado: ``n/a``.
    """
    try:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from ragas.dataset_schema import SingleTurnSample
            from ragas.metrics import IDBasedContextPrecision, IDBasedContextRecall
    except ImportError:
        return {"available": False, "reason": "RAGAS no está instalado (lo instala `pnpm test:harness:real`)"}
    recall_metric, precision_metric = IDBasedContextRecall(), IDBasedContextPrecision()
    recalls, precisions, gaps = [], [], []
    for case in cases:
        bundle = bundles.get(case.id)
        retrieved = (bundle[0] if isinstance(bundle, list) else bundle or {}).get(system)
        if not case.relevant or retrieved is None or retrieved.unavailable:
            continue
        ids = []
        for chunk in retrieved.chunks[:k]:
            ids.extend(i for i in matcher.ids(chunk["content"]) if not i.startswith("unmapped:") and i not in ids)
        sample = SingleTurnSample(retrieved_context_ids=ids or ["(vacío)"], reference_context_ids=list(case.relevant))
        recall = float(await recall_metric.single_turn_ascore(sample))
        recalls.append(Score(recall, recall, 1.0))
        precisions.append(Score(float(await precision_metric.single_turn_ascore(sample)), 0.0, 0.0))
        own = m.evidence_recall([matcher.ids(c["content"]) for c in retrieved.chunks], case.relevant, k)
        if own.applicable:
            gaps.append(abs(own.value - recall))
    return {
        "available": True,
        "system": system,
        "k": k,
        f"ragas_id_context_recall@{k}": aggregate(recalls),
        f"ragas_id_context_precision@{k}": aggregate([Score(p.value, p.value, 1.0) for p in precisions]),
        "max_gap_vs_evidence_recall": max(gaps) if gaps else None,
    }


def index_audit(corpus, chunk_texts, matcher, relevant_by_case=None) -> dict:
    """Qué parte del corpus alcanzan los fragmentos indexados (cota superior de recall).

    ``chunk_texts``: textos indexados (p. ej. ``kv_store_text_chunks.json``). Un segmento
    sin fragmento indexado que lo cubra no puede recuperarlo ningún modo de LightRAG.
    """
    covered: set = set()
    unmapped = 0
    for text in chunk_texts:
        ids = [x.segment_id for x in matcher.matches(text)]
        covered.update(ids)
        unmapped += not ids
    total = len(corpus.segments)
    report = {
        "indexed_chunks": len(chunk_texts),
        "chunks_without_segment": unmapped,
        "segments_total": total,
        "segments_covered": len(covered),
        "segment_coverage": len(covered) / total if total else None,
    }
    if relevant_by_case:
        needed = {sid for ids in relevant_by_case.values() for sid in ids}
        report["gold_segments"] = len(needed)
        report["gold_segments_covered"] = len(needed & covered)
        report["gold_segments_missing"] = sorted(needed - covered)
    return report


def corpus_quality(corpus, relevant_by_case=None) -> dict:
    """Documentos con OCR espaciado y cuántos segmentos del gold dependen de ellos."""
    gold_docs: dict = defaultdict(int)
    for ids in (relevant_by_case or {}).values():
        for sid in ids:
            gold_docs[corpus.segments[sid].doc_id] += 1
    docs = [
        {"doc_id": d.doc_id, "segments": len(d.segments), "spaced_ocr_ratio": round(d.spaced_ocr_ratio, 3),
         "gold_segments": gold_docs.get(d.doc_id, 0)}
        for d in corpus.documents.values()
    ]
    return {"documents": sorted(docs, key=lambda d: -d["spaced_ocr_ratio"]),
            "spaced_documents": [d["doc_id"] for d in docs if d["spaced_ocr_ratio"] > 0.5]}
