"""Puntuaciones por caso y agregación macro/micro con regla ``n/a``.

Una métrica sin denominador (p. ej. precisión de citas en una respuesta sin
citas) es ``n/a`` y **no** entra en ningún promedio: nunca se convierte en un 0
silencioso. Macro = media de los valores por caso evaluables. Micro = suma de
numeradores / suma de denominadores.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Score:
    """Resultado de una métrica en un caso (o en una muestra de un caso)."""

    value: Optional[float]
    num: float = 0.0
    den: float = 0.0
    na_reason: Optional[str] = None

    @classmethod
    def ratio(cls, num, den, na_reason="sin denominador"):
        if den <= 0:
            return cls.na(na_reason)
        return cls(num / den, float(num), float(den))

    @classmethod
    def flag(cls, hit: bool):
        return cls(1.0 if hit else 0.0, 1.0 if hit else 0.0, 1.0)

    @classmethod
    def na(cls, reason):
        return cls(None, 0.0, 0.0, reason)

    @property
    def applicable(self):
        return self.value is not None

    def to_json(self):
        data = {"value": self.value, "num": self.num, "den": self.den}
        if self.na_reason:
            data["na_reason"] = self.na_reason
        return data


def merge_samples(scores) -> Score:
    """Une las muestras de un mismo caso: media de los valores, num/den sumados."""
    applicable = [s for s in scores if s.applicable]
    if not applicable:
        return scores[0] if scores else Score.na("sin muestras")
    return Score(
        sum(s.value for s in applicable) / len(applicable),
        sum(s.num for s in applicable),
        sum(s.den for s in applicable),
    )


def aggregate(scores) -> dict:
    """``{"macro": {...}, "micro": {...}, "n": evaluables, "n_na": omitidos}``."""
    applicable = [s for s in scores if s.applicable]
    n_na = len(scores) - len(applicable)
    reasons = sorted({s.na_reason for s in scores if not s.applicable and s.na_reason})
    macro = (
        {"value": sum(s.value for s in applicable) / len(applicable), "n": len(applicable)}
        if applicable
        else {"value": None, "n": 0, "na_reason": "; ".join(reasons) or "sin casos evaluables"}
    )
    den = sum(s.den for s in applicable)
    micro = (
        {"value": sum(s.num for s in applicable) / den, "num": sum(s.num for s in applicable), "den": den}
        if den > 0
        else {"value": None, "num": 0, "den": 0, "na_reason": "; ".join(reasons) or "sin denominador"}
    )
    return {"macro": macro, "micro": micro, "n": len(applicable), "n_na": n_na}
