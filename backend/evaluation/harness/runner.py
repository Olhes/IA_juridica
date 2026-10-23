"""Orquestación de suites del harness y escritura de resultados reproducibles.

Resultados: ``temp/harness/<sha>/<suite>.json``, con sha, ``prompt_digest``,
revisión del corpus, hash del gold, modelos, juez y disponibilidad del juez.

CLI (lo invoca ``scripts/run-tests.mjs``):

    python -m evaluation.harness.runner legal_qa --cassette <ruta> [--run-model-evals]

Sin ``--run-model-evals`` solo reproduce un cassette; sin cassette falla en lugar
de llamar a ningún proveedor.
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from evaluation.harness.answers import Answer, answer_from_json, answer_from_payload
from evaluation.harness.cassettes import RECORD_MISSING, REPLAY, Cassette
from evaluation.harness.corpus import Corpus
from evaluation.harness.gold import LEGAL_QA_PATH, gold_hash, load_gold
from evaluation.harness.judges import make_judge
from evaluation.harness.pipeline_eval import evaluate_gold

ROOT = Path(__file__).resolve().parents[3]
RESULTS_DIR = ROOT / "temp" / "harness"
DEFAULT_CASSETTE = ROOT / "tests" / "backend" / "fixtures" / "gold" / "cassettes" / "legal_qa.cassette.json"


def _git(*args):
    try:
        out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=20)
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def git_identity() -> dict:
    sha = _git("rev-parse", "HEAD") or "unknown"
    return {"sha": sha, "dirty": bool(_git("status", "--porcelain", "--untracked-files=no")), "branch": _git("rev-parse", "--abbrev-ref", "HEAD")}


def collect_metadata(*, corpus, judge, samples, eval_mode, gold_path=LEGAL_QA_PATH, cassette=None) -> dict:
    from config.settings import settings
    from optimization.query_cache import pipeline_digest

    return {
        **git_identity(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "prompt_digest": pipeline_digest(),
        "corpus_revision": corpus.revision(),
        "gold_hash": gold_hash(gold_path),
        "models": {
            "llm": settings.COHERE_LLM_MODEL,
            "rerank": settings.COHERE_RERANK_MODEL,
            "embed": settings.COHERE_EMBED_MODEL,
            "temperature": 0.0 if eval_mode else settings.COHERE_TEMPERATURE,
        },
        "judge": judge.info(),
        "judge_available": judge.available,
        "eval_mode": eval_mode,
        "samples": samples,
        "answer_source": "cassette" if cassette is not None else "pipeline",
    }


def write_result(report: dict, meta: dict, suite: str, results_dir=RESULTS_DIR) -> Path:
    folder = Path(results_dir) / meta["sha"]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{suite}.json"
    path.write_text(json.dumps({"meta": meta, **report}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def cassette_answer_fn(cassette: Cassette, live_fn=None):
    """Respuesta desde el cassette; con modo de grabación, completa con ``live_fn``."""

    async def answer(case, sample) -> Answer:
        material = {"suite": "legal_qa", "case": case.id, "version": case.version, "query": case.query,
                    "language": case.language, "sample": sample}

        async def produce():
            return (await live_fn(case, sample)).to_json()

        return answer_from_json(await cassette.call(material, produce))

    return answer


async def build_live_answer_fn():
    """Pipeline real con el estado de la aplicación (red y coste: solo tras la autorización)."""
    import main  # noqa: PLC0415 - importa FastAPI y los proveedores solo si hace falta

    context = main.lifespan(main.app)
    await context.__aenter__()

    async def answer(case, sample) -> Answer:
        from services.legal_queries import answer_query

        payload = await answer_query(main.app.state, case.query, case.language, cache_key=None)
        return answer_from_payload(payload, case.language)

    answer.close = lambda: context.__aexit__(None, None, None)
    return answer


def apply_eval_mode():
    """EVAL_MODE=1: temperatura 0 y sin caché de respuestas (``cache_key=None``)."""
    from config.settings import settings

    settings.COHERE_TEMPERATURE = 0.0


async def run_legal_qa(*, splits=None, samples=1, judge_name="none", cassette_path=DEFAULT_CASSETTE, real=False, eval_mode=False, results_dir=RESULTS_DIR):
    corpus = Corpus.load()
    cases = load_gold(corpus=corpus, splits=splits)
    judge = make_judge(judge_name)
    cassette = Cassette(cassette_path, RECORD_MISSING if real else REPLAY)
    live = None
    if real:
        if eval_mode:
            apply_eval_mode()
        live = await build_live_answer_fn()
    try:
        report = await evaluate_gold(cases, cassette_answer_fn(cassette, live), corpus=corpus, judge=judge, samples=samples)
    finally:
        cassette.save()
        if live is not None:
            await live.close()
    meta = collect_metadata(corpus=corpus, judge=judge, samples=samples, eval_mode=eval_mode, cassette=cassette)
    return write_result(report, meta, "legal_qa", results_dir), report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", choices=["legal_qa"])
    parser.add_argument("--split", action="append", choices=["dev", "holdout"])
    parser.add_argument("--samples", type=int, default=None)
    parser.add_argument("--judge", default="none", choices=["none", "deepeval"])
    parser.add_argument("--cassette", default=str(DEFAULT_CASSETTE))
    parser.add_argument("--run-model-evals", action="store_true")
    args = parser.parse_args(argv)
    eval_mode = os.getenv("EVAL_MODE") == "1" or args.run_model_evals
    samples = args.samples or (3 if args.run_model_evals else 1)
    path, report = asyncio.run(
        run_legal_qa(splits=args.split, samples=samples, judge_name=args.judge, cassette_path=args.cassette,
                     real=args.run_model_evals, eval_mode=eval_mode)
    )
    headline = {k: v["macro"]["value"] for k, v in report["metrics"].items() if k in ("legal_factuality", "abstention_recall")}
    print(f"legal_qa: {report['n_cases']} casos, {report['n_errors']} errores -> {path}\n{headline}")
    return 1 if report["n_errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
