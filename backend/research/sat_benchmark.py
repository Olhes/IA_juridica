"""Ablación pareada sobre snapshot congelado y etiquetas externas al retriever.

Ejecutar desde raíz: python -m backend.research.sat_benchmark --help
con backend en PYTHONPATH (o invocar el archivo como se indica en la guía).
"""

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import platform
import random
import statistics
import sys
import time

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from retrieval.sat import (
    SATRetriever,
    SearchPlan,
    RankStages,
    bm25,
    fingerprint,
    ranked,
)
from retrieval.voyage import VoyageProvider, VoyageError, VoyageCacheMiss

STAGE_MODES = {
    "lexical": RankStages(dense=False, rerank=False),
    "dense_only": RankStages(dense=True, rerank=False),
    "rerank_only": RankStages(dense=False, rerank=True),
    "combined": RankStages(),
}


def score_case(expected: list[str], retrieved: list[str], *, answerable: bool, k=5):
    """IDs CTV distintos; un hit obsoleto nunca equivale a evidencia correcta."""
    unique_rank = list(dict.fromkeys(retrieved))[:k]
    gold, found = set(expected), set(unique_rank)
    matched = len(gold & found)
    dcg = sum(1 / math.log2(i + 2) for i, vid in enumerate(unique_rank) if vid in gold)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(len(gold), k)))
    return {
        "matched": matched,
        "gold": len(gold),
        "retrieved": len(found),
        "recall": matched / len(gold) if gold else None,
        "precision": matched / len(found) if found else None,
        "ndcg": dcg / ideal if ideal else None,
        "required_abstention": not answerable,
        "correct_abstention": not found and not answerable,
        "unnecessary_abstention": not found and answerable,
    }


def percentile(values, proportion):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * proportion
    low = int(position)
    return values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (
        position - low
    )


def paired_interval(deltas, *, seed=42):
    if not deltas:
        return None
    rng = random.Random(seed)
    means = [statistics.mean(rng.choices(deltas, k=len(deltas))) for _ in range(1000)]
    return {
        "mean_delta": statistics.mean(deltas),
        "bootstrap95": [percentile(means, 0.025), percentile(means, 0.975)],
        "pairs": len(deltas),
        "seed": seed,
        "resamples": 1000,
    }


def plan_model(dataset):
    if dataset["kind"] == "official_pdf_documentary":
        from research.documentary import DocumentaryPlan

        return DocumentaryPlan
    return SearchPlan


def score_reference_spans(references, hits, *, root_map=None):
    """Cobertura exacta del fragmento de referencia, no juicio de respuesta legal."""
    if not references:
        return None
    root_map = root_map or {}
    covered = sum(
        any(
            root_map.get(hit["version_id"], hit["version_id"]) == ref["version_id"]
            and hit.get("start", -1) <= ref["start"]
            and hit.get("end", -1) >= ref["end"]
            for hit in hits
        )
        for ref in references
    )
    return covered / len(references)


def validate_dataset(dataset):
    required = {"schema_version", "kind", "revision", "snapshot", "cases", "config"}
    if not required <= dataset.keys() or dataset["schema_version"] != 1:
        raise ValueError("Dataset incompleto")
    if dataset["kind"] not in {
        "synthetic_engineering",
        "legal_expert_reviewed",
        "official_pdf_documentary",
    }:
        raise ValueError("Declarar tipo de benchmark")
    documentary = dataset["kind"] == "official_pdf_documentary"
    level = dataset.get("evaluation_level", "version")
    if level not in {"version", "documentary_root"} or (
        level == "documentary_root" and not documentary
    ):
        raise ValueError("Nivel de evaluación inválido")
    root_map = {}
    if documentary:
        from research.documentary import validate_documentary_dataset

        validate_documentary_dataset(dataset)
        if level == "documentary_root":
            from research.documentary import documentary_root_map

            root_map = documentary_root_map(dataset["snapshot"])
    if not dataset["cases"] or len({c["id"] for c in dataset["cases"]}) != len(
        dataset["cases"]
    ):
        raise ValueError("Casos vacíos o duplicados")
    version_type = "DocumentaryVersion" if documentary else "CTV"
    ids = {n["id"] for n in dataset["snapshot"]["nodes"] if n["type"] == version_type}
    for case in dataset["cases"]:
        if not set(case["expected_version_ids"]) <= ids:
            raise ValueError("Gold refiere versión inexistente")
        if any(
            root_map.get(identity, identity) != identity
            for identity in case["expected_version_ids"]
        ):
            raise ValueError("Gold por raíz no admite IDs subordinados")
        if bool(case["expected_version_ids"]) != case["answerable"]:
            raise ValueError("Answerable contradice gold")
        if case["split"] not in {"development", "heldout"}:
            raise ValueError("Partición requerida")
        plan_model(dataset).model_validate({**dataset["config"], **case["plan"]})
        if documentary:
            from research.documentary import validate_references

            validate_references(dataset["snapshot"], case)


def flat_search(snapshot, plan):
    """Control BM25 sin tiempo, solo en harness; nunca se expone como ruta SAT."""
    nodes = {n["id"]: n for n in snapshot["nodes"]}
    texts, text_nodes = {}, {}
    for edge in snapshot["edges"]:
        if edge["type"] == "has_text":
            version, text = nodes[edge["source"]], nodes[edge["target"]]
            if version["type"] == (
                "DocumentaryVersion" if hasattr(plan, "source_ids") else "CTV"
            ):
                texts[version["id"]] = text["text"]
                text_nodes[version["id"]] = text
    ordered = ranked(bm25(plan.query, texts))[: plan.top_k]
    used, selected = 0, []
    for vid in ordered:
        content = texts[vid][: plan.chunk_chars]
        size = len(content.encode())
        if used + size <= plan.context_bytes:
            text = text_nodes[vid]
            selected.append(
                {
                    "version_id": vid,
                    "start": text["start"],
                    "end": text["start"] + len(content),
                    "content": content,
                }
            )
            used += size
    return {
        "hits": selected,
        "api": {"requests": 0, "tokens": 0, "cache_hits": 0},
    }


def prewarm_embeddings(engine, cases, config, provider):
    """Lotes REST normales (no Batch API); selección por elegibilidad, nunca gold."""
    groups, queries = {}, {}
    for case in cases:
        from research.documentary import DocumentaryPlan, DocumentaryRetriever

        model = (
            DocumentaryPlan if isinstance(engine, DocumentaryRetriever) else SearchPlan
        )
        plan = model.model_validate({**config, **case["plan"]})
        chunks = engine.chunks(plan)
        contextual = {}
        for chunk in chunks:
            contextual.setdefault(
                (chunk["resource_id"], chunk["version_id"]), []
            ).append(chunk)
        for values in contextual.values():
            group = [c["content"] for c in sorted(values, key=lambda c: c["start"])]
            groups[fingerprint(group)] = group
        if chunks:
            queries[plan.query] = [plan.query]
    usage = {"requests": 0, "tokens": 0, "cache_hits": 0}
    for values, kind in ((groups, "document"), (queries, "query")):
        if values:
            _, consumed = provider.embed(list(values.values()), input_type=kind)
            for key in usage:
                usage[key] += consumed[key]
    return usage


def run(
    dataset,
    *,
    provider=None,
    repetitions=3,
    split="development",
    prewarm=False,
    checkpoint=None,
    stages=None,
):
    stages = stages or RankStages()
    validate_dataset(dataset)
    if repetitions < 1:
        raise ValueError("Repeticiones positivas requeridas")
    if dataset["kind"] == "official_pdf_documentary":
        from research.documentary import DocumentaryRetriever

        engine = DocumentaryRetriever(dataset["snapshot"])
    else:
        engine = SATRetriever(dataset["snapshot"])
    root_map = {}
    if dataset.get("evaluation_level") == "documentary_root":
        from research.documentary import documentary_root_map

        root_map = documentary_root_map(dataset["snapshot"])
    cases = [case for case in dataset["cases"] if case["split"] == split]
    if not cases:
        raise ValueError("Partición sin casos")
    strategies = ["flat_bm25", "bm25", "metadata", "hybrid", "ppr", "tree"]
    records = []
    failures, provider_error = [], None
    preparation = {
        "enabled": bool(prewarm and provider and stages.dense),
        "api": None,
        "latency_ms": None,
    }
    for strategy in strategies:
        if strategy == "hybrid" and preparation["enabled"]:
            started = time.perf_counter()
            try:
                preparation["api"] = prewarm_embeddings(
                    engine, cases, dataset["config"], provider
                )
            except VoyageError as error:
                preparation["error"] = str(error)
                preparation["error_type"] = (
                    "cache_miss"
                    if isinstance(error, VoyageCacheMiss)
                    else "provider_error"
                )
                if not isinstance(error, VoyageCacheMiss):
                    provider_error = str(error)
            preparation["latency_ms"] = (time.perf_counter() - started) * 1000
        for case in cases:
            plan = plan_model(dataset).model_validate(
                {
                    **dataset["config"],
                    **case["plan"],
                    "strategy": "bm25" if strategy == "flat_bm25" else strategy,
                }
            )
            eligible = {c["version_id"] for c in engine.chunks(plan)}
            latencies, usage = [], {"requests": 0, "tokens": 0, "cache_hits": 0}
            stage_usage = {stage: dict(usage) for stage in ("dense", "rerank")}
            executions = []
            runs = []
            evaluation_runs, graph_runs, context_bytes, hit_spans = [], [], [], []
            reference_recalls = []
            error_message = (
                provider_error
                if provider
                and (stages.dense or stages.rerank)
                and strategy in {"hybrid", "ppr", "tree"}
                else None
            )
            error_type = "provider_error" if error_message else None
            for repetition in range(repetitions):
                if error_message:
                    break
                start = time.perf_counter()
                try:
                    output = (
                        flat_search(dataset["snapshot"], plan)
                        if strategy == "flat_bm25"
                        else engine.search(plan, provider=provider, stages=stages)
                    )
                except VoyageError as error:
                    # No transformar un fallo de API en abstención correcta o score cero.
                    error_message = str(error)
                    error_type = (
                        "cache_miss"
                        if isinstance(error, VoyageCacheMiss)
                        else "provider_error"
                    )
                    if not isinstance(error, VoyageCacheMiss):
                        provider_error = error_message
                    break
                latencies.append((time.perf_counter() - start) * 1000)
                runs.append([hit["version_id"] for hit in output["hits"]])
                hit_spans.append(
                    [
                        {key: hit[key] for key in ("version_id", "start", "end")}
                        for hit in output["hits"]
                    ]
                )
                evaluation_runs.append(
                    [root_map.get(identity, identity) for identity in runs[-1]]
                )
                graph_runs.append(output.get("ppr_status"))
                context_bytes.append(
                    sum(len(hit["content"].encode("utf-8")) for hit in output["hits"])
                )
                reference_recalls.append(
                    score_reference_spans(
                        case.get("reference_spans", []),
                        output["hits"],
                        root_map=root_map,
                    )
                )
                for key in usage:
                    usage[key] += output["api"][key]
                    for stage in stage_usage:
                        stage_usage[stage][key] += (
                            output.get("api_stages", {}).get(stage, {}).get(key, 0)
                        )
                executions.append(
                    {
                        stage: output.get(stage + "_status", "not_run")
                        for stage in stage_usage
                    }
                )
            if error_message:
                failure = {
                    "strategy": strategy,
                    "case_id": case["id"],
                    "status": "failed",
                    "error": error_message,
                    "error_type": error_type,
                    "completed_repetitions": len(runs),
                }
                failures.append(failure)
                if checkpoint:
                    checkpoint(failure)
                continue
            scores = score_case(
                case["expected_version_ids"],
                evaluation_runs[0],
                answerable=case["answerable"],
                k=plan.top_k,
            )
            records.append(
                {
                    "strategy": strategy,
                    "case_id": case["id"],
                    "stratum": case["stratum"],
                    "runs": runs,
                    "evaluation_runs": evaluation_runs,
                    "hit_spans": hit_spans,
                    "ppr_runs": graph_runs,
                    "context_bytes": context_bytes,
                    "stable_ranking": all(r == runs[0] for r in runs),
                    "scores": scores,
                    "reference_span_recall": reference_recalls[0],
                    "ineligible_returned": sorted(set(runs[0]) - eligible),
                    "latency_ms": latencies,
                    "api": usage,
                    "api_stages": stage_usage,
                    "stage_executions": executions,
                }
            )
            if checkpoint:
                checkpoint({"status": "completed", **records[-1]})
    summaries = {}
    baseline = {r["case_id"]: r for r in records if r["strategy"] == "flat_bm25"}
    for strategy in strategies:
        rows = [r for r in records if r["strategy"] == strategy]
        recalls = [
            r["scores"]["recall"] for r in rows if r["scores"]["recall"] is not None
        ]
        precisions = [
            r["scores"]["precision"]
            for r in rows
            if r["scores"]["precision"] is not None
        ]
        latency = [ms for r in rows for ms in r["latency_ms"]]
        negative = [r for r in rows if r["scores"]["required_abstention"]]
        deltas = [
            r["scores"]["recall"] - baseline[r["case_id"]]["scores"]["recall"]
            for r in rows
            if r["scores"]["recall"] is not None
        ]
        summaries[strategy] = {
            "cases": len(rows),
            "planned_cases": len(cases),
            "failed_cases": sum(f["strategy"] == strategy for f in failures),
            "answerable": len(recalls),
            "required_abstentions": len(negative),
            "macro_recall": statistics.mean(recalls) if recalls else None,
            "macro_reference_span_recall": (
                statistics.mean(
                    r["reference_span_recall"]
                    for r in rows
                    if r["reference_span_recall"] is not None
                )
                if any(r["reference_span_recall"] is not None for r in rows)
                else None
            ),
            "macro_precision_nonempty": (
                statistics.mean(precisions) if precisions else None
            ),
            "macro_ndcg_at_k": (
                statistics.mean(
                    r["scores"]["ndcg"] for r in rows if r["scores"]["ndcg"] is not None
                )
                if recalls
                else None
            ),
            "micro_matched": sum(r["scores"]["matched"] for r in rows),
            "micro_gold": sum(r["scores"]["gold"] for r in rows),
            "micro_retrieved": sum(r["scores"]["retrieved"] for r in rows),
            "ineligible_query_count": sum(bool(r["ineligible_returned"]) for r in rows),
            "correct_abstentions": sum(
                r["scores"]["correct_abstention"] for r in negative
            ),
            "unnecessary_abstentions": sum(
                r["scores"]["unnecessary_abstention"] for r in rows
            ),
            "latency_ms_p50": percentile(latency, 0.5),
            "latency_ms_p95": percentile(latency, 0.95),
            "first_pass_ms": [r["latency_ms"][0] for r in rows],
            "api": {
                key: sum(r["api"][key] for r in rows)
                for key in ("requests", "tokens", "cache_hits")
            },
            "paired_recall_vs_flat": paired_interval(deltas),
            "api_stages": {
                stage: {
                    key: sum(r["api_stages"][stage][key] for r in rows)
                    for key in ("requests", "tokens", "cache_hits")
                }
                for stage in ("dense", "rerank")
            },
        }
    return {
        "schema_version": 1,
        "status": "incomplete" if failures or preparation.get("error") else "completed",
        "run_at": datetime.now(timezone.utc).isoformat(),
        "dataset_kind": dataset["kind"],
        "evaluation_level": dataset.get("evaluation_level", "version"),
        "dataset_revision": dataset["revision"],
        "dataset_sha256": fingerprint(dataset),
        "snapshot_sha256": engine.revision,
        "config": dataset["config"],
        "split": split,
        "repetitions": repetitions,
        "provider": (
            "+".join(
                model
                for enabled, model in (
                    (stages.dense, "voyage-context-4"),
                    (stages.rerank, "rerank-3-lite"),
                )
                if enabled
            )
            if provider and (stages.dense or stages.rerank)
            else "none_offline"
        ),
        "provider_mode": (
            ("cache_only" if getattr(provider, "cache_only", False) else "live")
            if provider
            else "offline"
        ),
        "requested_stages": stages.model_dump(),
        "dimension": provider.dimension if provider else None,
        "preparation": preparation,
        "provider_ledger": provider.usage() if provider else None,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "concurrency": 1,
            "cache_policy": "persistent_first_pass_and_repeats_reported",
        },
        "summaries": summaries,
        "records": records,
        "failures": failures,
        "limitations": [
            "official_pdf_documentary mide ediciones PDF y gold documental IA; no resuelve vigencia jurídica.",
            "No compara con LightRAG: flat_bm25 es un control léxico independiente.",
            "PPR/tree son adaptaciones parciales, no reproducciones completas Three-Tier/Psi-RAG.",
            "Sin generación LLM ni evaluación de respuestas o traducción.",
            "Resultados sintéticos no prueban calidad jurídica ni sirven para autorizar producción.",
            "La cuota gratuita efectiva y cargos se comprueban en el dashboard, no aquí.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--voyage",
        action="store_true",
        help="Opt-in: envía corpus y consultas a Voyage, consume cuota",
    )
    mode.add_argument(
        "--cache-only",
        action="store_true",
        help="Reutiliza SQLite en solo lectura, sin clave ni red; misses no se puntúan",
    )
    parser.add_argument("--stages", choices=list(STAGE_MODES), default="combined")
    parser.add_argument(
        "--ppr-weight",
        type=float,
        default=1.0,
        help="Peso de PPR en RRF, entre 0 y 2; por defecto 1 (experimental).",
    )
    parser.add_argument(
        "--dimension", type=int, choices=[256, 512, 1024, 2048], default=1024
    )
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument(
        "--prewarm",
        action="store_true",
        help="Agrupa embeddings normales y separa coste de preparación",
    )
    parser.add_argument(
        "--split", choices=["development", "heldout"], default="development"
    )
    args = parser.parse_args(argv)
    try:
        stages = RankStages(
            **{**STAGE_MODES[args.stages].model_dump(), "ppr_weight": args.ppr_weight}
        )
    except ValueError as error:
        parser.error(f"Peso PPR inválido: {error}")
    provider = None
    if args.output.exists():
        parser.error("El informe ya existe; elegir salida nueva")
    if args.voyage:
        from dotenv import dotenv_values
        import os

        key = os.environ.get("VOYAGE_API_KEY") or dotenv_values(BACKEND / ".env").get(
            "VOYAGE_API_KEY", ""
        )
        provider = VoyageProvider(
            key,
            BACKEND / "docs/voyage_cache.sqlite3",
            dimension=args.dimension,
        )
    elif args.cache_only:
        provider = VoyageProvider(
            "",
            BACKEND / "docs/voyage_cache.sqlite3",
            dimension=args.dimension,
            cache_only=True,
        )
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Checkpoint append-only; una interrupción deja progreso sin afirmar run completo.
    with args.output.with_suffix(".progress.jsonl").open(
        "x", encoding="utf-8"
    ) as progress:

        def save_checkpoint(record):
            progress.write(
                json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n"
            )
            progress.flush()

        save_checkpoint(
            {
                "status": "started",
                "dataset_sha256": fingerprint(dataset),
                "split": args.split,
                "repetitions": args.repetitions,
                "dimension": args.dimension if provider else None,
                "requested_stages": stages.model_dump(),
                "provider_mode": (
                    "cache_only"
                    if args.cache_only
                    else ("live" if args.voyage else "offline")
                ),
            }
        )
        result = run(
            dataset,
            provider=provider,
            repetitions=args.repetitions,
            split=args.split,
            prewarm=args.prewarm,
            checkpoint=save_checkpoint,
            stages=stages,
        )
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "provider": result["provider"],
                "status": result["status"],
                "cases": next(iter(result["summaries"].values()))["cases"],
                "summaries": result["summaries"],
            },
            ensure_ascii=False,
        )
    )
    return result


def cli(argv=None):
    return 0 if main(argv)["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(cli())
