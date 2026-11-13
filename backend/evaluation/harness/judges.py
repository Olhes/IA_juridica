"""Contrato sin juez y funciones simuladas para las pruebas del evaluador."""

from typing import Optional

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
            "judge_failures": getattr(self, "judge_failures", 0),
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


def make_judge(name="none") -> Judge:
    if name == "none":
        return NoJudge()
    raise ValueError(f"Juez no disponible: {name}")
