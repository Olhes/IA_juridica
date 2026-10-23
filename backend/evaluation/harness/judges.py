"""Jueces configurables. Cada informe registra cuál corrió y si estuvo disponible.

``none`` (por defecto) no llama a ningún modelo. ``deepeval`` reutiliza el juez de
``evaluation/model_quality.py`` (``EVAL_JUDGE_MODEL`` + ``OPENAI_API_KEY``) y solo
puede crearse con la autorización explícita de red/coste (``--run-model-evals``).
Nunca corre en CI de pull request.
"""

import os
from typing import Optional


class Judge:
    name = "none"
    model: Optional[str] = None
    unavailable_reason: Optional[str] = "no se configuró ningún juez"

    @property
    def available(self) -> bool:
        return self.unavailable_reason is None

    def info(self) -> dict:
        return {
            "name": self.name,
            "model": self.model,
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
        }

    async def faithfulness(self, query, answer, contexts) -> Optional[float]:
        return None

    async def fact_present(self, answer, fact_text) -> Optional[bool]:
        return None


class NoJudge(Judge):
    pass


class CallableJudge(Judge):
    """Juez basado en funciones; lo usan los tests para ejercitar el contrato sin modelos."""

    name = "callable"
    unavailable_reason = None

    def __init__(self, faithfulness=None, fact_present=None, model="test-judge"):
        self.model = model
        self._faithfulness, self._fact_present = faithfulness, fact_present

    async def faithfulness(self, query, answer, contexts):
        return self._faithfulness(query, answer, contexts) if self._faithfulness else None

    async def fact_present(self, answer, fact_text):
        return self._fact_present(answer, fact_text) if self._fact_present else None


class DeepEvalJudge(Judge):
    name = "deepeval"

    def __init__(self, model=None):
        self.model = model or os.getenv("EVAL_JUDGE_MODEL", "").strip() or None
        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not self.model or not key:
            self.unavailable_reason = "falta EVAL_JUDGE_MODEL u OPENAI_API_KEY"
        else:
            self.unavailable_reason = None
            self._key = key

    def _llm(self):
        from deepeval.models import GPTModel

        return GPTModel(model=self.model, api_key=self._key)

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


def make_judge(name="none") -> Judge:
    if name == "none":
        return NoJudge()
    if name == "deepeval":
        return DeepEvalJudge()
    raise ValueError(f"Juez desconocido: {name}")
