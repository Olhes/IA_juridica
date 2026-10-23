"""Umbrales prerregistrados *después* de medir un baseline.

Este módulo no fija ningún número: solo ofrece el mecanismo. ``register`` exige un
resultado de baseline existente y guarda su identidad (sha, hash del archivo y del
gold) junto con la fecha de registro. ``check`` devuelve ``unregistered`` mientras no
haya umbrales —nunca un ``pass`` por omisión— y ``stale`` si el gold cambió.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from evaluation.harness.gold import GOLD_DIR

THRESHOLDS_PATH = GOLD_DIR / "thresholds.v1.json"
UNREGISTERED = {"schema": 1, "status": "unregistered", "baseline": None, "registered_at": None, "thresholds": {}}
SCOPES = ("macro", "micro")


class ThresholdError(ValueError):
    pass


def load_thresholds(path=THRESHOLDS_PATH) -> dict:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else dict(UNREGISTERED)


def _metric_value(report, metric, scope):
    entry = report.get("metrics", {}).get(metric)
    if not entry:
        return None
    return entry.get(scope, {}).get("value")


def register(baseline_path, thresholds: dict, out_path=THRESHOLDS_PATH, *, allow_unadjudicated=False, now=None) -> dict:
    """Prerregistra ``thresholds`` = ``{metric: {"scope": "macro", "min": x} | {"max": x}}``."""
    baseline_path = Path(baseline_path)
    if not baseline_path.exists():
        raise ThresholdError("No hay resultado de baseline: mide primero y registra después")
    raw = baseline_path.read_bytes()
    report = json.loads(raw)
    meta = report.get("meta", {})
    if not thresholds:
        raise ThresholdError("No se indicó ningún umbral")
    for metric, rule in thresholds.items():
        if rule.get("scope", "macro") not in SCOPES or not ({"min", "max"} & set(rule)):
            raise ThresholdError(f"Regla inválida para {metric}")
        if _metric_value(report, metric, rule.get("scope", "macro")) is None:
            raise ThresholdError(f"El baseline no mide {metric} (n/a): no se puede prerregistrar")
    adjudicated = report.get("gold", {}).get("adjudicated", 0)
    if not adjudicated and not allow_unadjudicated:
        raise ThresholdError("El baseline no usa casos adjudicados por abogados; los umbrales serían provisionales")
    document = {
        "schema": 1,
        "status": "registered",
        "provisional": not adjudicated,
        "baseline": {
            "sha": meta.get("sha"),
            "result_sha256": hashlib.sha256(raw).hexdigest(),
            "gold_hash": meta.get("gold_hash"),
            "prompt_digest": meta.get("prompt_digest"),
            "adjudicated_cases": adjudicated,
        },
        "registered_at": (now or datetime.now(timezone.utc)).isoformat(),
        "thresholds": thresholds,
    }
    Path(out_path).write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return document


def check(report: dict, document: dict) -> dict:
    """Compara ``report`` con los umbrales; ``status``: unregistered | stale | pass | fail."""
    if document.get("status") != "registered":
        return {"status": "unregistered", "checks": [], "reason": "no hay umbrales prerregistrados"}
    gold_hash = report.get("meta", {}).get("gold_hash")
    if gold_hash != document["baseline"]["gold_hash"]:
        return {"status": "stale", "checks": [], "reason": "el gold cambió desde el baseline; vuelve a medir y registrar"}
    checks = []
    for metric, rule in document["thresholds"].items():
        scope = rule.get("scope", "macro")
        value = _metric_value(report, metric, scope)
        if value is None:
            checks.append({"metric": metric, "scope": scope, "value": None, "ok": False, "reason": "n/a"})
            continue
        ok = ("min" not in rule or value >= rule["min"]) and ("max" not in rule or value <= rule["max"])
        checks.append({"metric": metric, "scope": scope, "value": value, "rule": {k: rule[k] for k in ("min", "max") if k in rule}, "ok": ok})
    return {"status": "pass" if all(c["ok"] for c in checks) else "fail", "checks": checks}
