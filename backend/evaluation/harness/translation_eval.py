"""Evalúa la traducción es→qu contra el gold paralelo.

``evaluate_translation`` recibe las salidas de un sistema (reales, de un cassette o
sintéticas) y devuelve métricas con regla ``n/a`` y agregación macro/micro, por tipo
de par, variante y split. Sistemas de referencia que no necesitan red: ``identity``
(copia el español; el piso de las métricas). Google Translate solo con
``--run-model-evals`` o desde un cassette.
"""

from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Optional

from evaluation.harness.metrics import translation as t
from evaluation.harness.metrics.common import Score, aggregate
from services.translation_qe import detect_language, estimate_quality

SCORED = ("chrf++", "bleu", "ter", "glossary", "references", "placeholder_leak", "language_ok", "copy_rate", "coverage", "round_trip")
HEADLINE = "chrf++"


@dataclass
class Output:
    text: str
    success: bool = True
    complete: bool = True
    back_translation: Optional[str] = None
    round_trip: Optional[float] = None  # coseno precalculado con embeddings (red solo al grabar)
    error: Optional[str] = None

    def to_json(self):
        return asdict(self)

    @classmethod
    def from_json(cls, data):
        return cls(**data)


def glossary_for(pairs, variant) -> list:
    """Entradas ``(término, alternativas)`` de los pares ``term`` de una variante."""
    return [(p.source_es, p.references_qu) for p in pairs if p.kind == "term" and p.variant == variant]


def language_id_check(pairs) -> dict:
    """Exactitud de la heurística de idioma sobre el propio gold (referencias qu, originales es)."""
    refs = [r for p in pairs for r in p.references_qu if len(r.split()) >= 4]
    sources = [p.source_es for p in pairs if len(p.source_es.split()) >= 4]
    qu_hits = sum(detect_language(r) == "qu" for r in refs)
    es_hits = sum(detect_language(s) == "es" for s in sources)
    return {
        "references": {"n": len(refs), "detected_qu": qu_hits, "rate": qu_hits / len(refs) if refs else None},
        "sources": {"n": len(sources), "detected_es": es_hits, "rate": es_hits / len(sources) if sources else None},
    }


def score_pair(pair, output: Output, glossary) -> dict:
    refs, text = pair.references_qu, output.text
    sentence = t.sentence_scores(text, refs)
    scores = {
        "chrf++": sentence["chrf++"], "bleu": sentence["bleu"], "ter": sentence["ter"],
        "glossary": t.glossary_adherence(pair.source_es, text, glossary),
        "references": t.references_kept(pair.source_es, text),
        "placeholder_leak": t.placeholder_leak(text),
        "language_ok": t.language_ok(text),
        "copy_rate": t.copy_score(pair.source_es, text),
        "coverage": t.coverage(refs, text),
        "round_trip": Score(output.round_trip, output.round_trip, 1.0) if output.round_trip is not None
        else Score.na("sin retrotraducción o sin embeddings"),
    }
    return scores


def _summarise(rows):
    return {name: aggregate([row[name] for row in rows]) for name in SCORED} if rows else {}


def evaluate_translation(pairs, outputs, *, system="unknown", only_clean=True) -> dict:
    """``outputs``: ``{pair_id: Output}``. Un par sin salida cuenta como error, no como 0."""
    evaluated = [p for p in pairs if not only_clean or p.reference_quality == "clean"]
    rows, errors = [], []
    glossaries: dict = {}
    for pair in evaluated:
        output = outputs.get(pair.id)
        if output is None or not output.success or not output.text.strip():
            errors.append({"pair_id": pair.id, "error": (output.error if output else None) or "sin salida"})
            continue
        glossary = glossaries.setdefault(pair.variant, glossary_for(pairs, pair.variant))
        # Un término no se evalúa contra sí mismo en el glosario.
        own = [(term, alts) for term, alts in glossary if not (pair.kind == "term" and term == pair.source_es)]
        rows.append({"pair": pair, "scores": score_pair(pair, output, own), "output": output})

    def corpus_block(selected):
        if not selected:
            return {}
        chrf_stats = [t.best_chrf_stats(r["output"].text, r["pair"].references_qu) for r in selected]
        merged = [tuple(sum(s[i][k] for s in chrf_stats) for k in range(3)) for i in range(len(chrf_stats[0]))]
        bleu = t.merge_bleu_stats([t.best_bleu_stats(r["output"].text, r["pair"].references_qu) for r in selected])
        return {"chrf++": t.chrf_from_stats(merged), "bleu": t.bleu_from_stats(bleu), "n": len(selected)}

    def group(key):
        groups = defaultdict(list)
        for row in rows:
            groups[key(row["pair"])].append(row)
        return {k: {"metrics": _summarise([r["scores"] for r in v]), "corpus": corpus_block(v)} for k, v in sorted(groups.items())}

    qualities = defaultdict(list)
    for row in rows:
        qe = estimate_quality(row["pair"].source_es, row["output"].text)
        qualities[qe["quality"]].append(row["scores"]["chrf++"].value)
    return {
        "suite": "translation",
        "system": system,
        "direction": "es>qu",
        "n_pairs": len(evaluated),
        "n_scored": len(rows),
        "n_errors": len(errors),
        "errors": errors,
        "gold": {
            "total": len(pairs),
            "status": dict(sorted(_count(pairs, lambda p: p.status).items())),
            "kind": dict(sorted(_count(pairs, lambda p: p.kind).items())),
            "variant": dict(sorted(_count(pairs, lambda p: p.variant).items())),
            "adjudicated": sum(p.status == "adjudicated" for p in pairs),
        },
        "metrics": _summarise([r["scores"] for r in rows]),
        "corpus": corpus_block(rows),
        "by_kind": group(lambda p: p.kind),
        "by_variant": group(lambda p: p.variant),
        "by_split": group(lambda p: p.split),
        "qe_vs_chrf": {q: {"n": len(v), "mean_chrf": sum(v) / len(v)} for q, v in sorted(qualities.items())},
        "language_id_gold": language_id_check(evaluated),
        "pairs": [
            {"id": r["pair"].id, "kind": r["pair"].kind, "variant": r["pair"].variant,
             "scores": {k: v.to_json() for k, v in r["scores"].items()}}
            for r in rows
        ],
    }


def _count(items, key):
    counts = defaultdict(int)
    for item in items:
        counts[key(item)] += 1
    return counts


def identity_outputs(pairs) -> dict:
    """Piso de referencia: «traducir» copiando el español."""
    return {p.id: Output(p.source_es) for p in pairs}
