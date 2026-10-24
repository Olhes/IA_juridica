"""¿Empeoró el asistente entre dos commits? Compara los resultados del harness de ``--base`` y ``--head``.

Para cada suite se parean los casos por ``id`` y se calcula, por métrica, el delta macro y micro con
un intervalo de confianza por *bootstrap pareado* (semilla fija). Un cambio solo cuenta si su IC
excluye el cero; con pocos casos (``MIN_PAIRS``) no se afirma nada. Veredicto: ``MEJORÓ``, ``IGUAL`` o
``EMPEORÓ``; es ``EMPEORÓ`` y **bloqueante** si aparecen afirmaciones prohibidas nuevas, si un caso fuera del
corpus deja de abstenerse o si cae la validez del stream. Se informa también qué cambió (``prompt_digest``,
corpus, modelos, juez, gold): si el gold o el juez difieren, la comparación se marca no comparable.

CLI: ``python -m evaluation.harness.compare --base v8 --head HEAD`` (ver ``main``).
"""

import argparse
import json
import random
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

N_BOOT = 2000
MIN_PAIRS = 8
EPSILON = 1e-9
IMPROVED, SAME, WORSE = "MEJORÓ", "IGUAL", "EMPEORÓ"

# (métrica, ámbito, mayor_es_mejor)
HEADLINE = {
    "legal_qa": [
        ("legal_factuality", "macro", True),
        ("fact_recall", "micro", True),
        ("forbidden_claim", "macro", False),
        ("abstention_recall", "macro", True),
        ("unnecessary_abstention", "macro", False),
        ("citation_in_corpus", "micro", True),
    ],
    "retrieval": [
        ("evidence_recall@5", "macro", True),
        ("ndcg@5", "macro", True),
        ("mrr", "macro", True),
        ("jurisprudence_hit@5", "macro", True),
    ],
    "translation": [("chrf++", "macro", True), ("ter", "macro", False), ("glossary", "macro", True)],
}
RETRIEVAL_SYSTEM = "current_reranked"
# Suites que se pueden ejecutar sin proveedores; `legal_qa` necesita un cassette o --run-model-evals.
OFFLINE_SUITES = ("retrieval", "translation", "stream")
STREAM_METRICS = [("valid_stream_rate", True), ("final_rate", True), ("error_rate", False)]
META_KEYS = ("prompt_digest", "corpus_revision", "models", "judge", "judge_available", "gold_hash", "samples", "eval_mode", "answer_source")
MUST_MATCH = ("gold_hash",)


# ── Extracción de valores por caso ────────────────────────────────────────

def per_case(report: dict, suite: str) -> dict:
    """``{case_id: {metric: (value, num, den)}}`` solo con las métricas aplicables."""
    rows: dict = {}
    if suite == "legal_qa":
        source = {c["id"]: c["scores"] for c in report.get("cases", [])}
    elif suite == "retrieval":
        source = report.get("cases", {}).get(RETRIEVAL_SYSTEM, {})
    elif suite == "translation":
        source = {p["id"]: p["scores"] for p in report.get("pairs", [])}
    else:
        return rows
    for case_id, scores in source.items():
        rows[case_id] = {
            name: (s["value"], s.get("num", 0.0), s.get("den", 0.0)) for name, s in scores.items() if s.get("value") is not None
        }
    return rows


# ── Bootstrap pareado ─────────────────────────────────────────────────────

def _stat(sample, scope):
    if scope == "macro":
        return sum(v for v, _, _ in sample) / len(sample)
    den = sum(d for _, _, d in sample)
    return sum(n for _, n, _ in sample) / den if den else None


def paired_delta(pairs, scope, *, n_boot=N_BOOT, seed=0) -> dict:
    """``pairs``: ``[((v,n,d) base, (v,n,d) head)]``. Delta head−base con IC95 por bootstrap pareado."""
    if not pairs:
        return {"n": 0, "base": None, "head": None, "delta": None, "ci": None}
    base = _stat([b for b, _ in pairs], scope)
    head = _stat([h for _, h in pairs], scope)
    if base is None or head is None:
        return {"n": len(pairs), "base": base, "head": head, "delta": None, "ci": None}
    rnd = random.Random(seed)
    deltas = []
    for _ in range(n_boot):
        picks = [pairs[rnd.randrange(len(pairs))] for _ in pairs]
        b, h = _stat([x for x, _ in picks], scope), _stat([y for _, y in picks], scope)
        if b is not None and h is not None:
            deltas.append(h - b)
    deltas.sort()
    ci = [deltas[int(0.025 * len(deltas))], deltas[min(int(0.975 * len(deltas)), len(deltas) - 1)]] if deltas else None
    return {"n": len(pairs), "base": base, "head": head, "delta": head - base, "ci": ci}


def classify(result: dict, higher_is_better: bool) -> str:
    """``better`` | ``worse`` | ``same`` | ``insufficient`` | ``n/a`` según el IC del delta."""
    if result["delta"] is None or result["ci"] is None:
        return "n/a"
    if result["n"] < MIN_PAIRS:
        return "insufficient"
    low, high = result["ci"]
    if low > EPSILON:
        return "better" if higher_is_better else "worse"
    if high < -EPSILON:
        return "worse" if higher_is_better else "better"
    return "same"


def compare_metric(base_rows: dict, head_rows: dict, metric: str, scope: str, higher: bool, *, seed=0) -> dict:
    ids = sorted(set(base_rows) & set(head_rows))
    pairs = [(base_rows[i][metric], head_rows[i][metric]) for i in ids if metric in base_rows[i] and metric in head_rows[i]]
    result = paired_delta(pairs, scope, seed=seed)
    return {"metric": metric, "scope": scope, "higher_is_better": higher, **result, "status": classify(result, higher)}


# ── Casos y bloqueos ──────────────────────────────────────────────────────

def case_changes(base_rows: dict, head_rows: dict, metric: str, higher: bool, *, threshold=0.05, limit=10) -> dict:
    moves = []
    for case_id in sorted(set(base_rows) & set(head_rows)):
        if metric in base_rows[case_id] and metric in head_rows[case_id]:
            delta = head_rows[case_id][metric][0] - base_rows[case_id][metric][0]
            if abs(delta) > threshold:
                moves.append({"case_id": case_id, "base": base_rows[case_id][metric][0], "head": head_rows[case_id][metric][0],
                              "delta": delta, "improved": delta > 0 if higher else delta < 0})
    moves.sort(key=lambda m: abs(m["delta"]), reverse=True)
    return {"metric": metric, "improved": [m for m in moves if m["improved"]][:limit], "regressed": [m for m in moves if not m["improved"]][:limit]}


def legal_qa_blocks(base: dict, head: dict) -> list:
    """Afirmaciones sin respaldo nuevas y abstenciones perdidas: bloquean aunque el promedio mejore."""
    blocks = []
    base_cases = {c["id"]: c for c in base.get("cases", [])}
    for case in head.get("cases", []):
        before = base_cases.get(case["id"])
        if before is None:
            continue
        new_hits = sorted(set(case.get("forbidden_hits", [])) - set(before.get("forbidden_hits", [])))
        if new_hits:
            blocks.append({"kind": "afirmación_nueva_sin_respaldo", "case_id": case["id"], "stratum": case.get("stratum"),
                           "detail": new_hits})
        was = (before["scores"].get("abstention_recall") or {}).get("value")
        now = (case["scores"].get("abstention_recall") or {}).get("value")
        if was is not None and now is not None and was >= 1.0 and now < 1.0:
            blocks.append({"kind": "dejó_de_abstenerse", "case_id": case["id"], "stratum": case.get("stratum"), "detail": []})
    return blocks


def stream_comparison(base: dict, head: dict) -> dict:
    rows, blocks = [], []
    for name, higher in STREAM_METRICS:
        b, h = base.get(name), head.get(name)
        status = "n/a" if b is None or h is None else "same" if abs(h - b) < EPSILON else ("better" if (h > b) == higher else "worse")
        rows.append({"metric": name, "scope": "stream", "higher_is_better": higher, "base": b, "head": h,
                     "delta": None if b is None or h is None else h - b, "ci": None, "n": head.get("n_streams"), "status": status})
    if base.get("valid_stream_rate") is not None and head.get("valid_stream_rate") is not None \
            and head["valid_stream_rate"] < base["valid_stream_rate"]:
        blocks.append({"kind": "cayó_la_validez_del_stream", "case_id": None, "stratum": None,
                       "detail": [base["valid_stream_rate"], head["valid_stream_rate"]]})
    latency = {s: {"base": (base.get("stage_ms", {}).get(s) or {}).get("p95"), "head": (head.get("stage_ms", {}).get(s) or {}).get("p95")}
               for s in ("retrieval", "generation", "validation")}
    return {"metrics": rows, "blocks": blocks, "latency_p95_ms": latency}


# ── Metadatos ─────────────────────────────────────────────────────────────

def meta_diff(base: dict, head: dict) -> dict:
    changed = {k: {"base": base.get(k), "head": head.get(k)} for k in META_KEYS if base.get(k) != head.get(k)}
    problems = []
    for key in MUST_MATCH:
        if key in changed:
            problems.append(f"`{key}` distinto: los resultados no miden el mismo gold")
    if (base.get("judge") or {}).get("name") != (head.get("judge") or {}).get("name"):
        problems.append("el juez cambió entre las dos mediciones")
    return {"changed": changed, "comparable": not problems, "problems": problems}


# ── Una suite ─────────────────────────────────────────────────────────────

def compare_suite(suite: str, base: dict, head: dict, *, seed=0) -> dict:
    out: dict = {"suite": suite, "meta": meta_diff(base.get("meta", {}), head.get("meta", {})), "metrics": [], "blocks": [], "cases": []}
    if suite == "stream":
        result = stream_comparison(base, head)
        out["metrics"], out["blocks"], out["latency_p95_ms"] = result["metrics"], result["blocks"], result["latency_p95_ms"]
        return out
    base_rows, head_rows = per_case(base, suite), per_case(head, suite)
    for metric, scope, higher in HEADLINE.get(suite, []):
        out["metrics"].append(compare_metric(base_rows, head_rows, metric, scope, higher, seed=seed))
        out["cases"].append(case_changes(base_rows, head_rows, metric, higher))
    if suite == "legal_qa":
        out["blocks"] = legal_qa_blocks(base, head)
    errors = (base.get("n_errors", 0), head.get("n_errors", 0))
    out["errors"] = {"base": errors[0], "head": errors[1], "worse": errors[1] > errors[0]}
    return out


def verdict(suites: list) -> dict:
    """Veredicto global a partir de las suites comparadas (las ausentes no suman ni restan)."""
    blocks = [dict(b, suite=s["suite"]) for s in suites for b in s["blocks"]]
    statuses = [(s["suite"], m["metric"], m["status"]) for s in suites for m in s["metrics"]]
    worse = [x for x in statuses if x[2] == "worse"]
    better = [x for x in statuses if x[2] == "better"]
    error_regressions = [s["suite"] for s in suites if s.get("errors", {}).get("worse")]
    if blocks or worse or error_regressions:
        label = WORSE
    elif better:
        label = IMPROVED
    else:
        label = SAME
    return {"verdict": label, "blocking": bool(blocks), "blocks": blocks, "worse": worse, "better": better,
            "error_regressions": error_regressions,
            "evidence": "suficiente" if any(m["status"] in ("better", "worse", "same") for s in suites for m in s["metrics"]) else "insuficiente"}


# ── Informe ───────────────────────────────────────────────────────────────

def _fmt(value, digits=3):
    return "n/a" if value is None else f"{value:.{digits}f}"


def render_markdown(report: dict) -> str:
    v = report["verdict"]
    lines = [f"# Comparación `{report['base']['ref']}` → `{report['head']['ref']}`", "",
             f"**Veredicto: {v['verdict']}**" + (" — **BLOQUEANTE**" if v["blocking"] else ""),
             f"Evidencia: {v['evidence']}. Base `{report['base']['sha'][:10]}`, head `{report['head']['sha'][:10]}`.", ""]
    if not report["comparable"]:
        lines += ["> ⚠ **No comparable:** " + "; ".join(report["incomparable_reasons"]), ""]
    if v["blocks"]:
        lines += ["## Bloqueos", ""]
        lines += [f"- `{b['suite']}` · {b['kind']}" + (f" · caso `{b['case_id']}`" if b.get("case_id") else "") + (f" ({b['stratum']})" if b.get("stratum") else "")
                  + (f": {', '.join(map(str, b['detail']))}" if b.get("detail") else "") for b in v["blocks"]]
        lines.append("")
    for suite in report["suites"]:
        lines += [f"## Suite `{suite['suite']}`", ""]
        if suite["meta"]["changed"]:
            lines += ["Cambios entre mediciones:", ""]
            for key, pair in suite["meta"]["changed"].items():
                lines.append(f"- `{key}`: `{pair['base']}` → `{pair['head']}`")
            lines.append("")
        lines += ["| Métrica | Ámbito | Base | Head | Δ | IC 95 % | n | Estado |", "|---|---|---|---|---|---|---|---|"]
        for m in suite["metrics"]:
            ci = "—" if not m.get("ci") else f"[{_fmt(m['ci'][0])}, {_fmt(m['ci'][1])}]"
            lines.append(f"| `{m['metric']}` | {m['scope']} | {_fmt(m['base'])} | {_fmt(m['head'])} | {_fmt(m['delta'])} | {ci} | {m.get('n') or 0} | {m['status']} |")
        lines.append("")
        for moves in suite.get("cases", []):
            if moves["regressed"] or moves["improved"]:
                lines.append(f"Casos que cambiaron en `{moves['metric']}`:")
                lines += [f"- ↓ `{c['case_id']}`: {_fmt(c['base'])} → {_fmt(c['head'])}" for c in moves["regressed"][:5]]
                lines += [f"- ↑ `{c['case_id']}`: {_fmt(c['base'])} → {_fmt(c['head'])}" for c in moves["improved"][:5]]
                lines.append("")
        if suite.get("latency_p95_ms"):
            lines += ["Latencia p95 por etapa (ms): " + ", ".join(f"{k} {_fmt(x['base'], 1)}→{_fmt(x['head'], 1)}" for k, x in suite["latency_p95_ms"].items()), ""]
    if report.get("ab"):
        ab = report["ab"]
        lines += ["## A/B ciego con orden invertido", "",
                  f"Casos: {ab['counts']}. Victorias del head sobre decisivos: {_fmt(ab['head_win_rate'])}; p (signo) = {_fmt(ab['sign_test_p'])}; "
                  f"sesgo de posición: {_fmt(ab['position_bias_rate'])}.", ""]
    if report["missing"]:
        lines += ["## Suites sin resultados", ""] + [f"- {item}" for item in report["missing"]] + [""]
    return "\n".join(lines).rstrip() + "\n"


# ── Orquestación de git y resultados ──────────────────────────────────────

OVERLAY = (
    "backend/evaluation/__init__.py",
    "backend/evaluation/harness",
    "backend/utils/text_match.py",
    "backend/services/citation_verifier.py",
    "backend/services/translation_qe.py",
    "tests/backend/fixtures/gold",
)


def git(repo: Path, *args) -> str:
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=120)
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} falló: {done.stderr.strip()[:200]}")
    return done.stdout.strip()


def resolve_sha(repo: Path, ref: str) -> str:
    return git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")


def overlay_harness(source_root: Path, worktree: Path) -> None:
    """Copia el harness actual al worktree: mide código antiguo con instrumentos nuevos, sin tocar su pipeline."""
    for relative in OVERLAY:
        origin, target = Path(source_root, relative), Path(worktree, relative)
        if not origin.exists():
            continue
        if origin.is_dir():
            shutil.copytree(origin, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin, target)


def run_suite_in_worktree(worktree: Path, suite: str, results_dir: Path, extra=()) -> int:
    import os

    env = dict(os.environ, PYTHONPATH=str(worktree / "backend"), PYTHONIOENCODING="utf-8")
    command = [sys.executable, "-m", "evaluation.harness.runner", suite, "--results-dir", str(results_dir), *extra]
    return subprocess.run(command, cwd=worktree / "backend", env=env, timeout=3600).returncode


def result_path(results_dir: Path, sha: str, suite: str) -> Path:
    return Path(results_dir) / sha / f"{suite}.json"


def worktree_path(sha: str, base: Optional[Path] = None) -> Path:
    """Ruta corta (Windows limita las rutas de git): ``<tmp>/iaj-wt-<sha8>``, no dentro de ``temp/harness``."""
    import tempfile

    return Path(base or tempfile.gettempdir()) / f"iaj-wt-{sha[:8]}"


def ensure_results(repo: Path, ref: str, suites, results_dir: Path, *, run_missing=False, extra=(), runner=run_suite_in_worktree,
                   worktree_base: Optional[Path] = None, runnable=None) -> dict:
    """Devuelve ``{suite: ruta|None}``; ejecuta en un ``git worktree`` temporal solo lo que falta y se pide."""
    sha = resolve_sha(repo, ref)
    found = {suite: (result_path(results_dir, sha, suite) if result_path(results_dir, sha, suite).exists() else None) for suite in suites}
    missing = [suite for suite, path in found.items() if path is None and (runnable is None or suite in runnable)]
    if missing and run_missing:
        worktree = worktree_path(sha, worktree_base)
        if worktree.exists():
            git(repo, "worktree", "remove", "--force", str(worktree))
        git(repo, "worktree", "add", "--detach", str(worktree), sha)
        try:
            overlay_harness(repo, worktree)
            for suite in missing:
                runner(worktree, suite, results_dir, extra)
                path = result_path(results_dir, sha, suite)
                found[suite] = path if path.exists() else None
        finally:
            git(repo, "worktree", "remove", "--force", str(worktree))
    return {"ref": ref, "sha": sha, "paths": found}


def build_report(base: dict, head: dict, *, suites=("legal_qa", "retrieval", "translation", "stream"), seed=0, ab=None) -> dict:
    compared, missing = [], []
    for suite in suites:
        b_path, h_path = base["paths"].get(suite), head["paths"].get(suite)
        if not b_path or not h_path:
            side = [name for name, path in (("base", b_path), ("head", h_path)) if not path]
            missing.append(f"`{suite}`: faltan resultados de {' y '.join(side)}")
            continue
        compared.append(compare_suite(suite, json.loads(Path(b_path).read_text(encoding="utf-8")),
                                      json.loads(Path(h_path).read_text(encoding="utf-8")), seed=seed))
    reasons = [f"{s['suite']}: {p}" for s in compared for p in s["meta"]["problems"]]
    return {
        "base": {"ref": base["ref"], "sha": base["sha"]},
        "head": {"ref": head["ref"], "sha": head["sha"]},
        "suites": compared,
        "missing": missing,
        "comparable": not reasons,
        "incomparable_reasons": reasons,
        "verdict": verdict(compared),
        "ab": ab,
    }


def write_report(report: dict, out_dir: Path) -> tuple:
    out_dir = Path(out_dir) / f"{report['base']['sha'][:10]}..{report['head']['sha'][:10]}"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path, md_path = out_dir / "report.json", out_dir / "report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    md_path.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    return json_path, md_path


def run_ab(base: dict, head: dict, report: dict, out_root: Path, *, judge_name="none", seed=0) -> Optional[dict]:
    """A/B ciego: con juez lo resuelve; sin juez escribe los ensayos ciegos y la clave para revisión humana."""
    import asyncio

    from evaluation.harness import ab
    from evaluation.harness.judges import make_judge

    paths = (base["paths"].get("legal_qa"), head["paths"].get("legal_qa"))
    if not all(paths):
        report["missing"].append("A/B: faltan los resultados de `legal_qa` de alguno de los commits")
        return None
    reports = [json.loads(Path(p).read_text(encoding="utf-8")) for p in paths]

    def answers(r):
        return {a["case_id"]: a["answer"]["text"] for a in r.get("answers", []) if a["sample"] == 0}

    queries = {c["id"]: c.get("query", "") for c in reports[1].get("cases", [])}
    trials = ab.build_trials(answers(reports[0]), answers(reports[1]), queries, seed=seed)
    judge = make_judge(judge_name)
    if not trials:
        return {"counts": {"base": 0, "head": 0, "tie": 0, "inconsistent": 0, "unjudged": 0}, "head_win_rate": None, "sign_test_p": None, "position_bias_rate": None, "note": "las respuestas son idénticas"}
    if not judge.available:
        folder = out_root / f"{report['base']['sha'][:10]}..{report['head']['sha'][:10]}"
        folder.mkdir(parents=True, exist_ok=True)
        blinded = "\n".join(json.dumps(t.blinded(), ensure_ascii=False) for t in trials) + "\n"
        (folder / "ab_trials.jsonl").write_text(blinded, encoding="utf-8", newline="\n")
        (folder / "ab_key.json").write_text(json.dumps([t.to_json() for t in trials], ensure_ascii=False, indent=1), encoding="utf-8")
        report["missing"].append(f"A/B: sin juez disponible; ensayos ciegos en `{folder / 'ab_trials.jsonl'}` y clave en `ab_key.json`")
        return None
    return ab.resolve(trials, asyncio.run(ab.judge_trials(judge, trials)))


def main(argv: Optional[list] = None, *, repo: Optional[Path] = None) -> int:
    from evaluation.harness.runner import ROOT, RESULTS_DIR

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--suites", default="legal_qa,retrieval,translation,stream")
    parser.add_argument("--run-missing", action="store_true", help="ejecuta en un worktree las suites sin resultados (offline salvo --run-model-evals)")
    parser.add_argument("--run-model-evals", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--ab", action="store_true", help="A/B ciego con orden invertido de las respuestas de legal_qa")
    parser.add_argument("--judge", default="none", choices=["none", "deepeval"])
    args = parser.parse_args(argv)
    repo = Path(repo or ROOT)
    suites = [s for s in args.suites.split(",") if s]
    extra = ["--run-model-evals"] if args.run_model_evals else []
    results_dir = Path(RESULTS_DIR)
    runnable = suites if args.run_model_evals else [s for s in suites if s in OFFLINE_SUITES]
    base = ensure_results(repo, args.base, suites, results_dir, run_missing=args.run_missing, extra=extra, runnable=runnable)
    head = ensure_results(repo, args.head, suites, results_dir, run_missing=args.run_missing, extra=extra, runnable=runnable)
    report = build_report(base, head, suites=suites, seed=args.seed)
    if args.ab:
        report["ab"] = run_ab(base, head, report, results_dir / "compare", judge_name=args.judge, seed=args.seed)
    json_path, md_path = write_report(report, results_dir / "compare")
    print(render_markdown(report))
    print(f"Informe: {md_path}\n         {json_path}")
    if not report["suites"]:
        return 3
    if report["verdict"]["blocking"] or report["verdict"]["verdict"] == WORSE:
        return 1
    return 0 if report["comparable"] else 2


if __name__ == "__main__":
    sys.exit(main())
