"""Publica las métricas del harness para la página pública ``/calidad``.

Solo se publica lo que se midió sobre un sistema real: las líneas base sintéticas («copiar el español»,
pipeline simulado) se declaran **no medidas** para no presentarlas como calidad. El archivo
(``docs/quality/published.json``) lleva agregados, nunca texto de consultas ni de respuestas, y deja a la vista
que los casos del gold son candidatos hasta que abogados y hablantes nativos los revisen.

``python -m evaluation.harness.publish [--sha <sha>]`` lo regenera desde ``temp/harness/<sha>/``.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REAL_SOURCES = {"pipeline", "cassette", "offline_engine"}
ROOT = Path(__file__).resolve().parents[3]
PUBLISHED_PATH = ROOT / "docs" / "quality" / "published.json"
NOTICES = (
    "Medición preliminar: los casos del gold son candidatos extraídos del corpus y aún no los revisaron abogados ni, en la traducción, hablantes nativos.",
    "Las métricas describen el corpus y los casos medidos; no certifican verdad jurídica ni sustituyen asesoría profesional.",
    "Un valor «no medido» significa que falta una evaluación real autorizada; no es un resultado.",
)
LEGAL_QA_METRICS = ("legal_factuality", "fact_recall", "forbidden_claim", "citation_in_corpus", "abstention_recall", "unnecessary_abstention")
RETRIEVAL_METRICS = ("evidence_recall@5", "chunk_precision@5", "ndcg@5", "mrr", "jurisprudence_hit@5", "empty_when_unanswerable")
TRANSLATION_METRICS = ("chrf++", "bleu", "ter", "glossary", "references", "language_ok")


def _value(entry: dict, scope: str = "macro") -> Optional[float]:
    return (entry or {}).get(scope, {}).get("value")


def _metrics(source: dict, names, scope="macro") -> dict:
    return {name: {"macro": _value(source.get(name), "macro"), "micro": _value(source.get(name), "micro"),
                   "n": (source.get(name) or {}).get("n", 0)} for name in names if name in source}


def not_measured(reason: str) -> dict:
    return {"measured": False, "reason": reason}


def publish_suite(suite: str, report: Optional[dict]) -> dict:
    if report is None:
        return not_measured("Aún no se ejecutó esta evaluación.")
    source = (report.get("meta") or {}).get("answer_source")
    if source not in REAL_SOURCES:
        reasons = {"identity_baseline": "Solo se midió la línea base «copiar el español»; falta evaluar el traductor real.",
                   "stub_pipeline": "Solo se midió el costo propio del stream con un pipeline simulado; falta medir latencia real."}
        return not_measured(reasons.get(source, "La medición no usó un sistema real."))
    base = {"measured": True, "answer_source": source, "created_at": (report.get("meta") or {}).get("created_at")}
    if suite == "legal_qa":
        return {**base, "n_cases": report.get("n_cases"), "n_errors": report.get("n_errors"), "gold": report.get("gold"),
                "judge": (report.get("meta") or {}).get("judge", {}).get("name"), "metrics": _metrics(report.get("metrics", {}), LEGAL_QA_METRICS),
                "calibration": {k: report.get("calibration", {}).get(k) for k in ("n", "ece", "brier")}}
    if suite == "retrieval":
        systems = {name: _metrics(metrics, RETRIEVAL_METRICS) for name, metrics in report.get("main", {}).items()
                   if any(_value(m) is not None for m in metrics.values())}
        note = "Motor local sin LightRAG ni reranker de Cohere." if report.get("source") == "offline" else None
        if report.get("ndcg_definition") == "binary_unique_segments_tie_averaged_v1":
            note = ((note + " ") if note else "") + (
                "nDCG@k evalúa k segmentos únicos con empates promediados; "
                "las métricas de cobertura y precisión usan k fragmentos. "
                "No comparar este nDCG con informes anteriores sin recalcularlos."
            )
        return {**base, "n_cases": report.get("n_cases"), "systems": systems, "note": note,
                "index_audit": {k: (report.get("index_audit") or {}).get(k) for k in ("indexed_chunks", "segment_coverage", "gold_segments", "gold_segments_covered")},
                "spaced_ocr_documents": len((report.get("corpus_quality") or {}).get("spaced_documents", []))}
    if suite == "translation":
        return {**base, "system": report.get("system"), "n_scored": report.get("n_scored"), "gold": report.get("gold"),
                "metrics": _metrics(report.get("metrics", {}), TRANSLATION_METRICS), "corpus": report.get("corpus")}
    if suite == "stream":
        return {**base, "n_streams": report.get("n_streams"), "valid_stream_rate": report.get("valid_stream_rate"),
                "ttfb_ms": report.get("ttfb_ms"), "terminal_ms": report.get("terminal_ms"), "stage_ms": report.get("stage_ms")}
    return not_measured("Suite desconocida.")


def build_published(results_dir: Path, sha: str) -> dict:
    reports, metas = {}, []
    for suite in ("legal_qa", "retrieval", "translation", "stream"):
        path = Path(results_dir) / sha / f"{suite}.json"
        reports[suite] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        if reports[suite]:
            metas.append(reports[suite].get("meta", {}))
    meta = {"dirty": any(m.get("dirty") for m in metas),
            **{key: next((m[key] for m in metas if m.get(key)), None) for key in ("prompt_digest", "corpus_revision")}}
    return {
        "schema": 1,
        "status": "preliminar",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sha": sha,
        "dirty": bool(meta.get("dirty")),
        "prompt_digest": meta.get("prompt_digest"),
        "corpus_revision": meta.get("corpus_revision"),
        "notices": list(NOTICES),
        "suites": {suite: publish_suite(suite, report) for suite, report in reports.items()},
    }


def write_published(published: dict, path: Path = PUBLISHED_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(published, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def main(argv=None) -> int:
    from evaluation.harness.runner import RESULTS_DIR, git_identity

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", default=None)
    args = parser.parse_args(argv)
    sha = args.sha or git_identity()["sha"]
    published = build_published(RESULTS_DIR, sha)
    print(f"Publicado en {write_published(published)}: " + ", ".join(f"{k}={'medido' if v['measured'] else 'no medido'}" for k, v in published["suites"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
