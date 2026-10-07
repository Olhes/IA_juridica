"""Evaluaciones de generación real con contexto controlado; sin fallback."""

import asyncio
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
DATASET = BACKEND.parent / "tests" / "backend" / "fixtures" / "quality_cases.json"


@dataclass(frozen=True)
class QualityCase:
    id: str
    input: str
    expected_output: str
    context: list[str]
    language: str = "spanish"


def load_cases(path=DATASET):
    cases = [
        QualityCase(**item)
        for item in json.loads(Path(path).read_text(encoding="utf-8"))
    ]
    if not cases or len({case.id for case in cases}) != len(cases):
        raise ValueError("El dataset debe contener casos con IDs únicos")
    for case in cases:
        if not isinstance(case.id, str) or not case.id.strip():
            raise ValueError("El caso necesita un ID no vacío")
        if (
            not case.input.strip()
            or not case.expected_output.strip()
            or not case.context
        ):
            raise ValueError(f"Caso incompleto: {case.id}")
        if not all(isinstance(text, str) and text.strip() for text in case.context):
            raise ValueError(f"Contexto vacío: {case.id}")
        if case.language not in {"spanish", "quechua"}:
            raise ValueError(f"Idioma no admitido: {case.id}")
    return cases


def require_credentials():
    from dotenv import load_dotenv

    # Solo se invoca después del opt-in. No muestra valores de credenciales.
    load_dotenv(BACKEND / ".env", override=False)
    missing = [
        name
        for name in ("COHERE_API_KEY", "OPENAI_API_KEY", "EVAL_JUDGE_MODEL")
        if not os.getenv(name, "").strip()
    ]
    if missing:
        raise ValueError("Falta configurar: " + ", ".join(missing))


async def generate_response(case):
    from agents.pydantic_agents import LegalAgent, get_system_prompt
    from config.settings import settings

    agent = LegalAgent()
    if agent.cohere_client is None:
        raise RuntimeError(
            "Cohere no inicializado; no se permite una respuesta de fallback"
        )
    context = {"answer": "\n".join(case.context), "sources": [case.id]}
    prompt = (
        get_system_prompt("general")
        + "\n"
        + agent._build_user_prompt(case.input, context, case.language)
    )
    # Mismo generador y prompts que el backend; contexto de benchmark, no corpus vivo.
    text = await agent._generate_text_with_cohere(
        case.input, context, case.language, "general"
    )
    return text, {
        "generation_model": agent.model_name,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "temperature": settings.COHERE_TEMPERATURE,
        "max_tokens": settings.COHERE_MAX_TOKENS,
    }


def create_suite(judge_model):
    from deepeval.models import GPTModel
    from evaluation.deepeval_tests import LegalEvaluationSuite

    # Proveedor del juez explícito: no depende del modelo predeterminado de DeepEval.
    judge = GPTModel(model=judge_model, api_key=os.environ["OPENAI_API_KEY"])
    return LegalEvaluationSuite(judge_model=judge)


async def evaluate_case(
    case, judge_model, *, timeout=180, generator=None, suite_factory=None
):
    from deepeval.test_case import LLMTestCase

    generator = generator or generate_response
    suite_factory = suite_factory or create_suite
    started = datetime.now(timezone.utc).isoformat()
    result = {
        "case_id": case.id,
        "input": case.input,
        "context": case.context,
        "expected_output": case.expected_output,
        "language": case.language,
        "judge_model": judge_model,
        "started_at": started,
        "dataset_case_sha256": hashlib.sha256(
            json.dumps(asdict(case), sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest(),
        "deepeval_version": version("deepeval"),
        "scope": "generator_with_controlled_context",
        "passed": False,
    }

    async def run():
        output, metadata = await generator(case)
        if not isinstance(output, str) or not output.strip():
            raise ValueError("Respuesta vacía del modelo")
        result.update(metadata)
        result["actual_output"] = output
        test_case = LLMTestCase(
            input=case.input,
            actual_output=output,
            expected_output=case.expected_output,
            context=case.context,
            retrieval_context=case.context,
        )
        suite = suite_factory(judge_model)
        result.update(await suite.run_single_evaluation(test_case))

    try:
        await asyncio.wait_for(run(), timeout=timeout)
    except Exception as error:
        # No guarda mensajes del SDK: podrían contener cabeceras, URLs o secretos.
        result["error"] = type(error).__name__
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    return result


def save_report(results, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    summary = {
        "total": len(results),
        "passed": sum(bool(r["passed"]) for r in results),
        "results": results,
    }
    json_path = directory / "results.json"
    json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# Calidad del modelo — contexto controlado",
        "",
        f"Casos aprobados: {summary['passed']}/{summary['total']}",
        "",
        "No certifica exactitud jurídica, recuperación RAG ni el pipeline HTTP completo.",
        "",
    ]
    for result in results:
        lines += [
            f"## {result['case_id']}",
            f"Estado: {'APROBADO' if result['passed'] else 'FALLÓ'}",
            f"Generador: {result.get('generation_model', 'no generado')}",
            f"Juez: {result['judge_model']}",
            "",
        ]
        for name, metric in result.get("metrics", {}).items():
            lines.append(
                f"- {name}: {metric.get('score')} (umbral {metric.get('threshold')}); "
                f"{'aprobada' if metric.get('passed') else 'falló'}"
            )
        if "error" in result:
            lines.append(f"- Error: {result['error']}")
        lines.append("")
    (directory / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return json_path
