"""Datos de las vistas de calidad: métricas publicadas y panel de administración.

Todo es de solo lectura sobre archivos del harness; si faltan (p. ej. en un despliegue sin ``tests/`` ni
``temp/``) las secciones se devuelven como no disponibles en lugar de inventar valores.
"""

import json
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]  # backend/services/quality_reports.py -> raíz del repositorio
PUBLISHED_PATH = REPO / "docs" / "quality" / "published.json"
RESULTS_DIR = REPO / "temp" / "harness"
MAX_BLOCKS = 20
MAX_QUEUE = 50

DEFAULT_PUBLISHED = {
    "schema": 1,
    "status": "sin_publicar",
    "notices": ["Todavía no hay métricas publicadas."],
    "suites": {},
}


def load_published(path: Path = PUBLISHED_PATH) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(DEFAULT_PUBLISHED)
    return data if isinstance(data, dict) else dict(DEFAULT_PUBLISHED)


def latest_comparison(results_dir: Path = RESULTS_DIR) -> Optional[dict]:
    reports = sorted(Path(results_dir).glob("compare/*/report.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in reports:
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        verdict = report.get("verdict", {})
        return {
            "base": report.get("base"),
            "head": report.get("head"),
            "verdict": verdict.get("verdict"),
            "blocking": bool(verdict.get("blocking")),
            "blocks": [
                {k: b.get(k) for k in ("suite", "kind", "case_id", "stratum")} for b in verdict.get("blocks", [])[:MAX_BLOCKS]
            ],
            "comparable": report.get("comparable"),
            "missing": report.get("missing", []),
            "suites": [
                {"suite": s["suite"], "metrics": [{k: m.get(k) for k in ("metric", "scope", "base", "head", "delta", "status")} for m in s["metrics"]]}
                for s in report.get("suites", [])
            ],
        }
    return None


def gold_status() -> dict:
    """Cuántos casos del gold esperan revisión humana (abogados) y cuántos pares esperan hablantes nativos."""
    try:
        from collections import Counter

        from evaluation.harness.gold import load_gold
        from evaluation.harness.translation_gold import load_pairs

        qa = Counter(c.status for c in load_gold(verify=False))
        translation = Counter(p.status for p in load_pairs(verify=False))
    except Exception:  # noqa: BLE001 - sin los archivos del gold el panel lo declara no disponible
        return {"available": False}
    return {
        "available": True,
        "legal_qa": dict(qa),
        "translation": dict(translation),
        "pending_lawyers": qa.get("candidate", 0) + qa.get("reviewed", 0),
        "pending_native_speakers": translation.get("candidate", 0) + translation.get("reviewed", 0),
    }


def admin_overview(feedback_store, stream_metrics, results_dir: Path = RESULTS_DIR) -> dict:
    queue = feedback_store.queue("pending")[:MAX_QUEUE]
    return {
        "comparison": latest_comparison(results_dir),
        "gold": gold_status(),
        "feedback": feedback_store.summary(),
        "feedback_queue": [
            {k: item.get(k) for k in ("id", "created_at", "reason", "comment", "language", "query", "answer", "evidence_status", "translation_quality")}
            for item in queue
        ],
        "stream": stream_metrics.summary(),
    }
