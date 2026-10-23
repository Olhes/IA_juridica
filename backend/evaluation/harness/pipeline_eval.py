"""Evalúa el pipeline completo (``answer_query``, sin HTTP) contra el gold ``legal_qa``.

``evaluate_gold`` es independiente de dónde sale la respuesta: recibe una función
``answer_fn(case, sample) -> Answer`` (real, reproducida de un cassette o sintética).
Un error al responder se cuenta como error del caso y **no** se convierte en 0.
"""

from collections import defaultdict

from evaluation.harness.answers import Answer
from evaluation.harness.gold import GoldCase
from evaluation.harness.judges import Judge, NoJudge
from evaluation.harness.metrics import abstention, citations, factuality, faithfulness
from evaluation.harness.metrics.calibration import calibration
from evaluation.harness.metrics.common import Score, aggregate, merge_samples

HEADLINE = (
    "legal_factuality",
    "fact_recall",
    "forbidden_claim",
    "citation_in_corpus",
    "citation_acceptable",
    "abstention_recall",
    "unnecessary_abstention",
)
DIAGNOSTIC = ("faithfulness_overlap", "faithfulness_judge", "fact_recall_judge", "citation_grounded", "abstention_formal")
ALL_METRICS = HEADLINE + DIAGNOSTIC


async def score_sample(case: GoldCase, answer: Answer, index, judge: Judge) -> dict:
    text = answer.text
    scores = {
        "fact_recall": factuality.fact_recall(case, text),
        "legal_factuality": factuality.legal_factuality(case, text),
        "forbidden_claim": factuality.forbidden_claim(case, text),
        "citation_in_corpus": citations.citation_in_corpus(text, index),
        "citation_acceptable": citations.citation_acceptable(case, text),
        "citation_grounded": citations.citation_grounded(answer),
        "abstention_recall": abstention.abstention_recall(case, answer),
        "unnecessary_abstention": abstention.unnecessary_abstention(case, answer),
        "abstention_formal": abstention.formal_abstention(case, answer),
        "faithfulness_overlap": faithfulness.faithfulness_overlap(answer),
    }
    faithful = None
    fact_scores = None
    if judge.available:
        contexts = [s for s in answer.sources if isinstance(s, str)]
        faithful = await judge.faithfulness(case.query, text, contexts)
        if case.required_facts and not case.must_abstain:
            verdicts = [await judge.fact_present(text, f.text) for f in case.required_facts]
            if all(v is not None for v in verdicts):
                fact_scores = Score.ratio(sum(bool(v) for v in verdicts), len(verdicts))
    scores["faithfulness_judge"] = faithfulness.faithfulness_judge(faithful)
    scores["fact_recall_judge"] = fact_scores or Score.na("juez no disponible o caso sin hechos")
    return scores


def _group(results, key):
    groups = defaultdict(list)
    for item in results:
        groups[key(item)].append(item)
    return groups


def _aggregate_metrics(items):
    return {name: aggregate([r["scores"][name] for r in items if name in r["scores"]]) for name in ALL_METRICS}


async def evaluate_gold(cases, answer_fn, *, corpus, judge=None, samples=1) -> dict:
    """Devuelve el informe de la suite (JSON-serializable)."""
    judge = judge or NoJudge()
    index = citations.CorpusIndex(corpus)
    results, errors, answers = [], [], []
    for case in cases:
        per_sample, case_answers = [], []
        for sample in range(samples):
            try:
                answer = await answer_fn(case, sample)
            except Exception as error:  # noqa: BLE001 - se informa el tipo, nunca el mensaje
                errors.append({"case_id": case.id, "sample": sample, "error": type(error).__name__})
                continue
            case_answers.append(answer)
            answers.append({"case_id": case.id, "sample": sample, "answer": answer.to_json()})
            per_sample.append(await score_sample(case, answer, index, judge))
        if not per_sample:
            continue
        scores = {name: merge_samples([s[name] for s in per_sample]) for name in ALL_METRICS}
        passes = [factuality.factual_pass(case, a.text) for a in case_answers]
        confidences = [a.confidence_score for a in case_answers]
        results.append(
            {
                "case": case,
                "scores": scores,
                "factual_pass": None if any(p is None for p in passes) else sum(passes) / len(passes),
                "confidence": next((c for c in confidences if c is not None), None),
                "forbidden": sorted({h for a in case_answers for h in factuality.forbidden_hits(case, a.text)}),
                "missing_facts": sorted(
                    {f for a in case_answers for f, ok in factuality.covered_facts(case, a.text).items() if not ok}
                ) if not case.must_abstain else [],
            }
        )
    pairs = [
        (r["confidence"], r["factual_pass"] == 1.0)
        for r in results
        if r["confidence"] is not None and r["factual_pass"] is not None
    ]
    by_topic = _group(results, lambda r: r["case"].topic)
    return {
        "suite": "legal_qa",
        "n_cases": len(results),
        "n_errors": len(errors),
        "errors": errors,
        "samples": samples,
        "judge": judge.info(),
        "gold": {
            "total": len(cases),
            "status": dict(sorted(_count(cases, lambda c: c.status).items())),
            "stratum": dict(sorted(_count(cases, lambda c: c.stratum).items())),
            "split": dict(sorted(_count(cases, lambda c: c.split).items())),
            "adjudicated": sum(c.status == "adjudicated" for c in cases),
        },
        "metrics": _aggregate_metrics(results),
        "by_stratum": {k: _aggregate_metrics(v) for k, v in sorted(_group(results, lambda r: r["case"].stratum).items())},
        "by_split": {k: _aggregate_metrics(v) for k, v in sorted(_group(results, lambda r: r["case"].split).items())},
        "by_topic": {k: _aggregate_metrics(v) for k, v in sorted(by_topic.items())},
        "calibration": calibration(pairs),
        "cases": [
            {
                "id": r["case"].id,
                "stratum": r["case"].stratum,
                "split": r["case"].split,
                "topic": r["case"].topic,
                "status": r["case"].status,
                "factual_pass": r["factual_pass"],
                "forbidden_hits": r["forbidden"],
                "missing_facts": r["missing_facts"],
                "scores": {k: v.to_json() for k, v in r["scores"].items()},
            }
            for r in results
        ],
        "answers": answers,
    }


def _count(cases, key):
    counts = defaultdict(int)
    for case in cases:
        counts[key(case)] += 1
    return counts
