"""Evalúa el pipeline completo (``answer_query``, sin HTTP) contra el gold ``legal_qa``.

``evaluate_gold`` es independiente de dónde sale la respuesta: recibe una función
``answer_fn(case, sample) -> Answer`` (real, reproducida de un cassette o sintética).
Un error al responder se cuenta como error del caso y **no** se convierte en 0.
"""

from collections import defaultdict

from evaluation.harness.answers import Answer
from evaluation.harness.gold import GoldCase
from evaluation.harness.judges import Judge, NoJudge
from evaluation.harness.metrics import abstention, citations, factuality, faithfulness, translation
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
DIAGNOSTIC = (
    "faithfulness_overlap",
    "faithfulness_judge",
    "fact_recall_judge",
    "citation_grounded",
    "abstention_formal",
    "quechua_delivered",
    "query_language_detected",
    "ragas_faithfulness",
)
ALL_METRICS = HEADLINE + DIAGNOSTIC


def quechua_delivered(case: GoldCase, answer: Answer) -> Score:
    """En una consulta en quechua, ¿el usuario recibió quechua y no el español sin traducir?"""
    if case.language != "quechua":
        return Score.na("consulta en español")
    if case.must_abstain or answer.abstained_formal:
        return Score.na("abstención: no hay respuesta que traducir")
    translated = bool(answer.text.strip()) and answer.text.strip() != (answer.text_es or "").strip()
    return Score.flag(translated and bool(translation.language_ok(answer.text).value))


def query_language_detected(case: GoldCase) -> Score:
    """¿El detector del pipeline clasifica bien el idioma de la consulta? El pipeline solo traduce
    la consulta (qu→es) cuando la detecta como quechua: un quechua no detectado se recupera sin
    traducir y un español detectado como quechua se traduce sin motivo."""
    from modules.language.services.language_detector import LanguageDetector

    is_quechua = LanguageDetector().detect_language(case.query) == "qu"
    return Score.flag(is_quechua == (case.language == "quechua"))


async def score_sample(case: GoldCase, answer: Answer, index, judge: Judge) -> dict:
    # Hechos, citas y fidelidad se comprueban sobre la respuesta validada en español; en una
    # consulta en quechua ``answer.text`` es su traducción y se evalúa con ``quechua_delivered``.
    text = answer.fact_text
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
        "quechua_delivered": quechua_delivered(case, answer),
        "query_language_detected": query_language_detected(case),
    }
    faithful = None
    fact_scores = None
    contexts = [c for c in (answer.contexts or []) if isinstance(c, str) and c.strip()]
    if judge.available:
        if contexts:
            faithful = await judge.faithfulness(case.query, text, contexts)
        if case.required_facts and not case.must_abstain:
            verdicts = [await judge.fact_present(text, f.text) for f in case.required_facts]
            if all(v is not None for v in verdicts):
                fact_scores = Score.ratio(sum(bool(v) for v in verdicts), len(verdicts))
    scores["faithfulness_judge"] = faithfulness.faithfulness_judge(faithful)
    ragas_value = await judge.ragas_faithfulness(case.query, text, contexts) if judge.available and contexts else None
    scores["ragas_faithfulness"] = (
        Score.na("RAGAS no disponible") if ragas_value is None else Score(float(ragas_value), float(ragas_value), 1.0)
    )
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
        passes = [factuality.factual_pass(case, a.fact_text) for a in case_answers]
        confidences = [a.confidence_score for a in case_answers]
        results.append(
            {
                "case": case,
                "scores": scores,
                "factual_pass": None if any(p is None for p in passes) else sum(passes) / len(passes),
                "confidence": next((c for c in confidences if c is not None), None),
                "forbidden": sorted({h for a in case_answers for h in factuality.forbidden_hits(case, a.fact_text)}),
                "missing_facts": sorted(
                    {f for a in case_answers for f, ok in factuality.covered_facts(case, a.fact_text).items() if not ok}
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
