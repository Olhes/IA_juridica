"""Jueces configurables. Cada informe registra cuál corrió y si estuvo disponible.

``none`` (por defecto) no llama a ningún modelo. ``deepeval`` usa DeepEval (fidelidad y
hechos con G-Eval) y, si está instalado, RAGAS (fidelidad) como segunda lectura
independiente. El proveedor del juez sale de ``EVAL_JUDGE_PROVIDER``:

- ``cohere`` (por defecto): ``COHERE_API_KEY`` y ``EVAL_JUDGE_MODEL`` (por defecto
  ``command-a-03-2025``, más capaz que el generador ``command-r7b``).
- ``openai``: ``OPENAI_API_KEY`` y ``EVAL_JUDGE_MODEL`` (obligatorio).

Solo puede crearse con la autorización explícita de red/coste (``--run-model-evals``).
Nunca corre en CI de pull request.
"""

import asyncio
import os
from typing import Optional

COHERE_DEFAULT_JUDGE = "command-a-03-2025"
# API de Cohere compatible con OpenAI: la usa RAGAS (Instructor) sin dependencias nuevas.
COHERE_COMPAT_URL = "https://api.cohere.ai/compatibility/v1"


class Judge:
    name = "none"
    model: Optional[str] = None
    provider: Optional[str] = None
    unavailable_reason: Optional[str] = "no se configuró ningún juez"
    ragas_unavailable_reason: Optional[str] = "no se configuró ningún juez"

    @property
    def available(self) -> bool:
        return self.unavailable_reason is None

    def info(self) -> dict:
        return {
            "name": self.name,
            "provider": self.provider,
            "model": self.model,
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
            "ragas_available": self.available and self.ragas_unavailable_reason is None,
            "ragas_unavailable_reason": self.ragas_unavailable_reason,
            "ragas_failures": getattr(self, "ragas_failures", 0),
        }

    async def faithfulness(self, query, answer, contexts) -> Optional[float]:
        return None

    async def ragas_faithfulness(self, query, answer, contexts) -> Optional[float]:
        """Fidelidad según RAGAS; ``None`` si RAGAS o el juez no están disponibles."""
        return None

    async def fact_present(self, answer, fact_text) -> Optional[bool]:
        return None

    async def prefer(self, query, answer_a, answer_b) -> Optional[str]:
        """Preferencia ciega entre dos respuestas: ``A``, ``B``, ``tie`` o ``None`` (sin juez)."""
        return None


class NoJudge(Judge):
    pass


class CallableJudge(Judge):
    """Juez basado en funciones; lo usan los tests para ejercitar el contrato sin modelos."""

    name = "callable"
    unavailable_reason = None

    def __init__(self, faithfulness=None, fact_present=None, prefer=None, ragas_faithfulness=None, model="test-judge"):
        self.model = model
        self._faithfulness, self._fact_present, self._prefer = faithfulness, fact_present, prefer
        self._ragas = ragas_faithfulness
        self.ragas_unavailable_reason = None if ragas_faithfulness else "sin función RAGAS"

    async def prefer(self, query, answer_a, answer_b):
        return self._prefer(query, answer_a, answer_b) if self._prefer else None

    async def faithfulness(self, query, answer, contexts):
        return self._faithfulness(query, answer, contexts) if self._faithfulness else None

    async def ragas_faithfulness(self, query, answer, contexts):
        return self._ragas(query, answer, contexts) if self._ragas else None

    async def fact_present(self, answer, fact_text):
        return self._fact_present(answer, fact_text) if self._fact_present else None


def _cohere_llm_class():
    """Adaptador de Cohere para DeepEval (se define al usarse: DeepEval es pesado)."""
    from deepeval.models import DeepEvalBaseLLM

    class CohereJudgeLLM(DeepEvalBaseLLM):
        def __init__(self, model, api_key):
            self._api_key = api_key
            super().__init__(model)

        def load_model(self):
            import cohere

            return cohere.AsyncClientV2(api_key=self._api_key)

        def get_model_name(self):
            return f"cohere:{self.name}"

        async def _chat(self, prompt, response_format=None):
            kwargs = {"response_format": response_format} if response_format else {}
            reply = await self.model.chat(
                model=self.name, messages=[{"role": "user", "content": prompt}], temperature=0, **kwargs
            )
            return "".join(getattr(part, "text", "") or "" for part in (reply.message.content or []))

        async def a_generate(self, prompt, schema=None, **_):
            if schema is None:
                return await self._chat(prompt)
            try:
                text = await self._chat(
                    prompt, {"type": "json_object", "json_schema": schema.model_json_schema()}
                )
            except Exception:  # noqa: BLE001 - esquemas con $defs: se pide JSON libre y se valida igual
                text = await self._chat(
                    prompt + "\n\nResponde solo con un objeto JSON válido que cumpla este esquema:\n"
                    + str(schema.model_json_schema()),
                    {"type": "json_object"},
                )
            return schema.model_validate_json(text)

        def generate(self, prompt, schema=None, **kwargs):
            return asyncio.run(self.a_generate(prompt, schema=schema, **kwargs))

    return CohereJudgeLLM


class DeepEvalJudge(Judge):
    name = "deepeval"

    def __init__(self, model=None, provider=None):
        self.provider = (provider or os.getenv("EVAL_JUDGE_PROVIDER", "") or "cohere").strip().lower()
        if self.provider not in {"cohere", "openai"}:
            raise ValueError(f"Proveedor de juez desconocido: {self.provider}")
        default = COHERE_DEFAULT_JUDGE if self.provider == "cohere" else None
        self.model = model or os.getenv("EVAL_JUDGE_MODEL", "").strip() or default
        key_name = "COHERE_API_KEY" if self.provider == "cohere" else "OPENAI_API_KEY"
        self._key = os.getenv(key_name, "").strip()
        if not self.model or not self._key:
            self.unavailable_reason = f"falta EVAL_JUDGE_MODEL o {key_name}"
        else:
            self.unavailable_reason = None
        self._ragas_metric = None
        self.ragas_failures = 0
        self.ragas_unavailable_reason = self.unavailable_reason or self._ragas_import_problem()

    @staticmethod
    def _ragas_import_problem():
        try:
            import ragas  # noqa: F401
        except ImportError:
            return "RAGAS no está instalado (lo instala `pnpm test:harness:real`)"
        return None

    def _llm(self):
        if self.provider == "cohere":
            return _cohere_llm_class()(self.model, self._key)
        from deepeval.models import GPTModel

        return GPTModel(model=self.model, api_key=self._key)

    def _ragas(self):
        if self._ragas_metric is None:
            import instructor
            from openai import AsyncOpenAI
            from ragas.llms.base import InstructorLLM, InstructorModelArgs
            from ragas.metrics.collections import Faithfulness

            client = (
                AsyncOpenAI(api_key=self._key, base_url=COHERE_COMPAT_URL)
                if self.provider == "cohere"
                else AsyncOpenAI(api_key=self._key)
            )
            # Modo JSON: la API compatible de Cohere rechaza el modo de herramientas de Instructor.
            llm = InstructorLLM(
                client=instructor.from_openai(client, mode=instructor.Mode.JSON),
                model=self.model,
                provider="openai",
                model_args=InstructorModelArgs(temperature=0),
            )
            self._ragas_metric = Faithfulness(llm=llm)
        return self._ragas_metric

    async def faithfulness(self, query, answer, contexts):
        if not self.available:
            return None
        from deepeval.metrics import FaithfulnessMetric
        from deepeval.test_case import LLMTestCase

        metric = FaithfulnessMetric(model=self._llm(), include_reason=False)
        await metric.a_measure(
            LLMTestCase(input=query, actual_output=answer, retrieval_context=list(contexts))
        )
        return float(metric.score)

    async def ragas_faithfulness(self, query, answer, contexts):
        if not self.available or self.ragas_unavailable_reason:
            return None
        for _ in range(2):  # la API devuelve a veces un 422 transitorio en modo JSON
            try:
                result = await self._ragas().ascore(
                    user_input=query, response=answer, retrieved_contexts=list(contexts)
                )
            except Exception:  # noqa: BLE001 - se cuenta el fallo; nunca un 0 inventado
                continue
            value = getattr(result, "value", result)
            return None if value is None else float(value)
        self.ragas_failures += 1
        return None

    async def fact_present(self, answer, fact_text):
        if not self.available:
            return None
        from deepeval.metrics import GEval
        from deepeval.test_case import LLMTestCase, LLMTestCaseParams

        metric = GEval(
            name="hecho-presente",
            criteria=(
                "El texto de salida afirma, con otras palabras, el hecho indicado en la "
                "salida esperada, sin contradecirlo."
            ),
            evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT],
            model=self._llm(),
            threshold=0.5,
        )
        await metric.a_measure(LLMTestCase(input="", actual_output=answer, expected_output=fact_text))
        return bool(metric.success)

    async def prefer(self, query, answer_a, answer_b):
        if not self.available:
            return None
        prompt = (
            "Eres un revisor jurídico imparcial. Compara dos respuestas a la misma consulta y elige la más "
            "fiel a las fuentes y menos propensa a inventar afirmaciones. Responde únicamente A, B o EMPATE."
            + "\n\nConsulta: " + query
            + "\n\nRespuesta A:\n" + answer_a
            + "\n\nRespuesta B:\n" + answer_b
        )
        try:
            reply = await self._llm().a_generate(prompt)
            text = (reply[0] if isinstance(reply, tuple) else reply).strip().upper()
        except Exception:  # noqa: BLE001 - sin veredicto fiable no se inventa uno
            return None
        return "A" if text.startswith("A") else "B" if text.startswith("B") else "tie" if text.startswith("EMPATE") else None


def make_judge(name="none") -> Judge:
    if name == "none":
        return NoJudge()
    if name == "deepeval":
        return DeepEvalJudge()
    raise ValueError(f"Juez desconocido: {name}")
