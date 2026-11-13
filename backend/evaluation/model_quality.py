"""Carga y valida el conjunto de casos de calidad con contexto controlado."""

import json
from dataclasses import dataclass
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
