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
from evaluation.harness.corpus import DEFAULT_CORPUS_DIR, Corpus
from evaluation.harness.gold import LEGAL_QA_PATH, gold_hash, load_gold
from evaluation.harness.judges import make_judge
from evaluation.harness import retrieval_eval, retrieval_gold, translation_eval, translation_gold
from evaluation.harness.overlap import SegmentMatcher
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
    from evaluation.harness.digest import pipeline_digest

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


def write_result(report: dict, meta: dict, suite: str, results_dir=None) -> Path:
    results_dir = results_dir or RESULTS_DIR
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


DEFAULT_RETRIEVAL_CASSETTE = ROOT / "tests" / "backend" / "fixtures" / "gold" / "cassettes" / "retrieval.cassette.json"
KG_CHUNKS = ROOT / "backend" / "docs" / "knowledge_graph" / "kv_store_text_chunks.json"


def offline_engine(corpus_dir):
    """Motor con el corpus procesado y sin red: solo recuperación léxica y rerank de respaldo."""
    import tempfile

    from config.settings import settings
    from modules.rag.services.lightrag_engine import LegalRAGEngine

    previous, settings.LOAD_LOCAL_KG = settings.LOAD_LOCAL_KG, False
    try:
        engine = LegalRAGEngine(working_dir=tempfile.mkdtemp(prefix="harness-kg-"))
    finally:
        settings.LOAD_LOCAL_KG = previous
    engine._ensure_initialized = lambda: None
    engine.cohere_client = None
    for path in sorted(Path(corpus_dir).glob("*.md")):
        content = path.read_text(encoding="utf-8")
        engine.documents[path.stem] = {
            "content": content,
            "metadata": {"filename": path.name, "title": path.stem, "document_type": "legal_document"},
            "chunks": engine._chunk_content(content),
        }
    return engine


async def run_retrieval(*, source="offline", cassette_path=DEFAULT_RETRIEVAL_CASSETTE, results_dir=RESULTS_DIR, kg_chunks=KG_CHUNKS):
    """``source``: ``offline`` (motor local sin red), ``cassette`` (reproduce) o ``live`` (red/coste)."""
    from config.settings import settings

    corpus = Corpus.load()
    cases = retrieval_gold.build_from_legal_qa(corpus)
    matcher = SegmentMatcher(corpus)
    top_k, budget = settings.RERANK_TOP_K, settings.RERANK_CANDIDATES
    bundles: dict = {}
    cassette = Cassette(cassette_path, RECORD_MISSING if source == "live" else REPLAY) if source != "offline" else None
    engine, live = None, None
    if source == "offline":
        engine = offline_engine(DEFAULT_CORPUS_DIR)
    elif source == "live":
        import main  # noqa: PLC0415

        live = main.lifespan(main.app)
        await live.__aenter__()
        engine = main.app.state.rag_engine
    try:
        for case in cases:
            material = {"suite": "retrieval", "case": case.id, "query": case.query, "budget": budget, "top_k": top_k,
                        "embed": settings.COHERE_EMBED_MODEL, "rerank": settings.COHERE_RERANK_MODEL}

            async def produce(case=case):
                found = await retrieval_eval.retrieve_bundle(engine, case.query, budget=budget, top_k=top_k)
                return {name: item.to_json() for name, item in found.items()}

            raw = await produce() if cassette is None else await cassette.call(material, produce)
            bundles[case.id] = {name: retrieval_eval.Retrieved.from_json(item) for name, item in raw.items()}
    finally:
        if cassette is not None:
            cassette.save()
        if live is not None:
            await live.__aexit__(None, None, None)
    report = retrieval_eval.evaluate_retrieval(cases, bundles, matcher)
    relevant = {c.id: c.relevant for c in cases}
    report["corpus_quality"] = retrieval_eval.corpus_quality(corpus, relevant)
    if Path(kg_chunks).exists():
        stored = json.loads(Path(kg_chunks).read_text(encoding="utf-8"))
        report["index_audit"] = retrieval_eval.index_audit(corpus, [c.get("content", "") for c in stored.values()], matcher, relevant)
    report["source"] = source
    meta = collect_metadata(corpus=corpus, judge=make_judge("none"), samples=1, eval_mode=source == "live",
                            gold_path=retrieval_gold.RETRIEVAL_PATH if retrieval_gold.RETRIEVAL_PATH.exists() else LEGAL_QA_PATH,
                            cassette=cassette)
    meta["answer_source"] = {"offline": "offline_engine", "cassette": "cassette", "live": "pipeline"}[source]
    return write_result(report, meta, "retrieval", results_dir), report


async def run_stream_suite(*, source="offline", results_dir=RESULTS_DIR, splits=None, limit=None):
    """``offline``: pipeline simulado (mide el costo propio del stream). ``live``: pipeline real (red/coste)."""
    from evaluation.harness import stream_eval  # commits anteriores a F0 no tienen el contrato: solo falla esta suite

    corpus = Corpus.load()
    cases = load_gold(corpus=corpus, splits=splits)[:limit]
    live = None
    if source == "live":
        import main  # noqa: PLC0415

        live = main.lifespan(main.app)
        await live.__aenter__()
    records = []
    try:
        for case in cases:
            if live is None:
                run = stream_eval.stub_pipeline(case)
            else:
                from services.legal_queries import answer_query

                async def run(on_stage, case=case):
                    return await answer_query(main.app.state, case.query, case.language, cache_key=None, on_stage=on_stage)

            records.append(await stream_eval.run_stream(case.id, run_pipeline=run, language=case.language))
    finally:
        if live is not None:
            await live.__aexit__(None, None, None)
    report = {"suite": "stream", "source": source, **stream_eval.summarise_streams(records)}
    meta = collect_metadata(corpus=corpus, judge=make_judge("none"), samples=1, eval_mode=source == "live")
    meta["answer_source"] = "stub_pipeline" if source == "offline" else "pipeline"
    return write_result(report, meta, "stream", results_dir), report


DEFAULT_TRANSLATION_CASSETTE = ROOT / "tests" / "backend" / "fixtures" / "gold" / "cassettes" / "translation.cassette.json"


async def _embed_cosine(first, second):
    """Coseno entre embeddings de Cohere (red); ``None`` si no se puede calcular."""
    try:
        import cohere

        from config.settings import settings
        from evaluation.harness.metrics.translation import cosine

        client = cohere.AsyncClient(api_key=settings.COHERE_API_KEY)
        response = await client.embed(texts=[first, second], model=settings.COHERE_EMBED_MODEL,
                                      input_type="search_document", embedding_types=["float"])
        vectors = response.embeddings.float_
        return cosine(vectors[0], vectors[1])
    except Exception:  # noqa: BLE001 - la métrica queda n/a, no se inventa un valor
        return None


async def live_translation(pair) -> dict:
    """Google Translate (vía ``TranslationService``) más retrotraducción y coseno: red y coste."""
    from modules.language.services.translation_service import TranslationService

    service = TranslationService()
    result = await service.translate(pair.source_es, "es", "qu")
    output = translation_eval.Output(
        text=result.get("translated_text", "") if result.get("success") else "",
        success=bool(result.get("success")), complete=bool(result.get("complete")), error=result.get("error"),
    )
    if output.success:
        back = await service.translate(output.text, "qu", "es")
        if back.get("success"):
            output.back_translation = back.get("translated_text")
            output.round_trip = await _embed_cosine(pair.source_es, output.back_translation)
    return output.to_json()


async def run_translation(*, source="offline", cassette_path=DEFAULT_TRANSLATION_CASSETTE, results_dir=RESULTS_DIR, splits=None):
    """``source``: ``offline`` (solo la línea base «copiar el español»), ``cassette`` o ``live``."""
    corpus = Corpus.load()
    pairs = translation_gold.load_pairs(splits=splits)
    cassette = Cassette(cassette_path, RECORD_MISSING if source == "live" else REPLAY) if source != "offline" else None
    outputs: dict = {}
    for pair in pairs:
        if cassette is None:
            outputs[pair.id] = translation_eval.Output(pair.source_es)
            continue
        material = {"suite": "translation", "pair": pair.id, "version": pair.version, "provider": "google_translate",
                    "direction": "es>qu"}

        async def produce(pair=pair):
            return await live_translation(pair)

        try:
            outputs[pair.id] = translation_eval.Output.from_json(await cassette.call(material, produce))
        except Exception as error:  # noqa: BLE001 - un par sin grabar es un error del par, no un 0
            outputs[pair.id] = translation_eval.Output("", success=False, error=type(error).__name__)
    if cassette is not None:
        cassette.save()
    system = "identity" if cassette is None else "google_translate"
    report = translation_eval.evaluate_translation(pairs, outputs, system=system)
    report["source"] = source
    judge = make_judge("none")
    meta = collect_metadata(corpus=corpus, judge=judge, samples=1, eval_mode=source == "live",
                            gold_path=translation_gold.TRANSLATION_PATH, cassette=cassette)
    meta["answer_source"] = {"offline": "identity_baseline", "cassette": "cassette", "live": "google_translate"}[source]
    return write_result(report, meta, "translation", results_dir), report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", choices=["legal_qa", "retrieval", "translation", "stream"])
    parser.add_argument("--split", action="append", choices=["dev", "holdout"])
    parser.add_argument("--samples", type=int, default=None)
    parser.add_argument("--judge", default="none", choices=["none", "deepeval"])
    parser.add_argument("--cassette", default=str(DEFAULT_CASSETTE))
    parser.add_argument("--source", default="offline", choices=["offline", "cassette"], help="retrieval: motor local o cassette")
    parser.add_argument("--retrieval-cassette", default=str(DEFAULT_RETRIEVAL_CASSETTE))
    parser.add_argument("--translation-cassette", default=str(DEFAULT_TRANSLATION_CASSETTE))
    parser.add_argument("--results-dir", default=str(RESULTS_DIR), help="carpeta base de temp/harness/<sha>/")
    parser.add_argument("--run-model-evals", action="store_true")
    args = parser.parse_args(argv)
    eval_mode = os.getenv("EVAL_MODE") == "1" or args.run_model_evals
    samples = args.samples or (3 if args.run_model_evals else 1)
    if args.suite == "stream":
        path, report = asyncio.run(run_stream_suite(source="live" if args.run_model_evals else "offline", results_dir=args.results_dir))
        print(f"stream ({report['source']}) -> {path}")
        print(f"validos: {report['valid_stream_rate']}  ttfb p95: {report['ttfb_ms']['p95']}")
        return 0 if report["valid_stream_rate"] == 1.0 else 1
    if args.suite == "translation":
        source = "live" if args.run_model_evals else args.source
        path, report = asyncio.run(run_translation(source=source, cassette_path=args.translation_cassette, results_dir=args.results_dir))
        print(f"translation ({report['system']}) -> {path}")
        print(f"chrF++ macro: {report['metrics']['chrf++']['macro']['value']}")
        return 0
    if args.suite == "retrieval":
        source = "live" if args.run_model_evals else args.source
        path, report = asyncio.run(run_retrieval(source=source, cassette_path=args.retrieval_cassette, results_dir=args.results_dir))
        main_metrics = report["main"].get("lexical", {})
        recall = {k: v["macro"]["value"] for k, v in main_metrics.items() if k.startswith("evidence_recall")}
        print(f"retrieval ({source}) -> {path}")
        print(f"lexical@{report['main_k']}: {recall}")
        return 0
    path, report = asyncio.run(
        run_legal_qa(splits=args.split, samples=samples, judge_name=args.judge, cassette_path=args.cassette,
                     real=args.run_model_evals, eval_mode=eval_mode, results_dir=args.results_dir)
    )
    headline = {k: v["macro"]["value"] for k, v in report["metrics"].items() if k in ("legal_factuality", "abstention_recall")}
    print(f"legal_qa: {report['n_cases']} casos, {report['n_errors']} errores -> {path}\n{headline}")
    return 1 if report["n_errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
