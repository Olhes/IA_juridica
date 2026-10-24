"""Gold paralelo español→quechua (``translation.v1.jsonl``) y su verificación de procedencia.

Los pares salen de fuentes impresas (manuales del Ministerio de Cultura y edición
quechua-castellano de la Ley 30364). El gold **no** es una verdad lingüística: cada
par marca su variante y queda ``candidate`` hasta que dos hablantes nativos lo
revisen a ciegas. El cargador comprueba que el español y el quechua de cada par
aparecen en su archivo de origen, para que nada se invente.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from evaluation.harness.gold import GOLD_DIR, GoldValidationError
from utils.text_match import compact

TRANSLATION_PATH = GOLD_DIR / "translation.v1.jsonl"
SOURCES_DIR = Path(__file__).resolve().parents[2] / "docs" / "processed_backup"

Kind = Literal["sentence", "article", "title", "term"]
Variant = Literal["cusco-collao", "chanka", "sureno-sin-confirmar", "central"]
Quality = Literal["clean", "uncertain"]

_PAGE_NOISE = (
    re.compile(r"^<!--.*-->$"),
    re.compile(r"^- \d+ -$"),
    re.compile(r"^30364 Kamachiy Qillqa$", re.I),
)


def strip_page_noise(text: str) -> str:
    """Quita marcadores de página que la maquetación inserta a mitad de un párrafo."""
    lines = [ln for ln in text.replace("\r\n", "\n").split("\n") if not any(p.match(ln.strip()) for p in _PAGE_NOISE)]
    return "\n".join(lines)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Origin(_Model):
    file: str
    locator: str


class NativeReviewer(_Model):
    id: str = Field(min_length=1)
    role: Literal["hablante_nativo"]
    variant: str
    blind: bool
    verdict: Literal["approve", "revise", "reject"]
    reviewed_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class TranslationPair(_Model):
    schema_version: Literal[1] = 1
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")
    version: int = Field(ge=1)
    status: Literal["candidate", "reviewed", "adjudicated"]
    reviewers: list[NativeReviewer]
    kind: Kind
    variant: Variant
    reference_quality: Quality
    source_es: str = Field(min_length=2)
    references_qu: list[str] = Field(min_length=1)
    origin: Origin
    split: Literal["dev", "holdout"]
    notes: str = ""

    @model_validator(mode="after")
    def _consistency(self):
        if self.status == "candidate" and self.reviewers:
            raise ValueError("un par `candidate` no puede tener revisores")
        if self.status == "adjudicated":
            ids = {r.id for r in self.reviewers}
            if len(ids) < 2 or not all(r.blind and r.verdict == "approve" for r in self.reviewers):
                raise ValueError("`adjudicated` exige >= 2 hablantes nativos distintos, ciegos y que aprueban")
        if self.status == "reviewed" and not self.reviewers:
            raise ValueError("`reviewed` exige al menos un revisor")
        if any(not r.strip() for r in self.references_qu):
            raise ValueError("referencias vacías")
        return self


_COMPACT_CACHE: dict = {}


def _compact_source(path: Path) -> str:
    if path not in _COMPACT_CACHE:
        _COMPACT_CACHE[path] = compact(strip_page_noise(path.read_text(encoding="utf-8")))
    return _COMPACT_CACHE[path]


def verify_pair(pair: TranslationPair, sources_dir=SOURCES_DIR) -> list:
    """Problemas de ``pair`` frente a su archivo de origen (lista vacía si se sustenta)."""
    path = Path(sources_dir) / pair.origin.file
    if not path.exists():
        return [f"{pair.id}: no existe el origen {pair.origin.file}"]
    text, problems = _compact_source(path), []
    if not compact(pair.source_es) in text:
        problems.append(f"{pair.id}: el español no aparece en {pair.origin.file}")
    for reference in pair.references_qu:
        if compact(reference) not in text:
            problems.append(f"{pair.id}: el quechua {reference[:40]!r} no aparece en {pair.origin.file}")
    return problems


def load_pairs(path=TRANSLATION_PATH, *, verify=True, sources_dir=SOURCES_DIR, kinds=None, splits=None,
               only_clean=False, only_adjudicated=False) -> list:
    problems, pairs = [], []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            pairs.append(TranslationPair.model_validate_json(line))
        except ValidationError as error:
            problems.append(f"línea {number}: {error.errors(include_url=False)[0]['msg']}")
    ids = [p.id for p in pairs]
    if len(ids) != len(set(ids)):
        problems.append("hay `id` repetidos")
    if verify:
        for pair in pairs:
            problems.extend(verify_pair(pair, sources_dir))
    if problems:
        raise GoldValidationError(problems)
    return [
        p for p in pairs
        if (not kinds or p.kind in kinds) and (not splits or p.split in splits)
        and (not only_clean or p.reference_quality == "clean") and (not only_adjudicated or p.status == "adjudicated")
    ]


def translation_hash(path=TRANSLATION_PATH) -> str:
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:16]


def dump_pairs(pairs, path=TRANSLATION_PATH):
    lines = [json.dumps(p.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) for p in sorted(pairs, key=lambda p: p.id)]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
