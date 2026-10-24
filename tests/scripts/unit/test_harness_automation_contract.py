"""CI del harness: sin proveedores en los PR y evaluación real con puerta explícita."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"


def workflow(name):
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def steps(flow):
    return [step for job in flow["jobs"].values() for step in job["steps"]]


def triggers(flow):
    return flow.get("on", flow.get(True))  # PyYAML lee `on` como True


def commands(flow):
    return "\n".join(step.get("run", "") for step in steps(flow))


def test_pull_request_ci_runs_the_offline_suites_and_never_touches_providers():
    flow = workflow("ci.yml")
    assert "pull_request" in triggers(flow)
    run = commands(flow)
    assert "pnpm test\n" in run + "\n" and "pnpm test:harness" in run and "pnpm test:e2e" in run
    raw = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    assert "--run-model-evals" not in raw and "secrets." not in raw and "vars." not in raw
    assert flow["permissions"] == {"contents": "read"}


def test_real_evaluation_is_gated_by_schedule_label_or_manual_dispatch_and_always_confirms_cost():
    flow = workflow("harness-real.yml")
    when = triggers(flow)
    assert set(when) == {"schedule", "pull_request", "workflow_dispatch"} and when["pull_request"]["types"] == ["labeled"]
    assert when["schedule"][0]["cron"]
    condition = flow["jobs"]["evaluate"]["if"]
    assert "'eval'" in condition and "github.repository" in condition  # solo PR del propio repositorio con la etiqueta
    run = commands(flow)
    assert "pnpm test:harness:real --run-model-evals" in run
    assert "pnpm test:harness:compare" in run and "--ab" in run
    assert flow["permissions"] == {"contents": "read"} and flow["concurrency"]["cancel-in-progress"] is False
    secrets = set(re.findall(r"secrets\.(\w+)", (WORKFLOWS / "harness-real.yml").read_text(encoding="utf-8")))
    assert secrets == {"COHERE_API_KEY"}  # el juez usa Cohere: sin claves de otros proveedores
    assert flow["jobs"]["evaluate"]["env"]["EVAL_JUDGE_PROVIDER"] == "cohere"
    checkout = next(s for s in steps(flow) if str(s.get("uses", "")).startswith("actions/checkout"))
    assert checkout["with"]["fetch-depth"] == 0  # la comparación necesita la historia

