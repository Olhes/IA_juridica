"""Gold de recuperación (``retrieval.v1.jsonl``), derivado de ``legal_qa``.

``relevant`` = segmentos que sustentan los hechos exigidos (esenciales);
``supporting`` = segmentos de referencia adicionales (p. ej. donde consta una
cita); ``jurisprudence`` = los relevantes o de apoyo que son jurisprudencia
(citan una Casación o pertenecen a un documento sobre una Casación). Un caso que
exige abstención no tiene segmentos relevantes: sus métricas de evidencia son
``n/a``. Hereda el estado de ``legal_qa``: mientras sea ``candidate`` no es verdad.
"""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from evaluation.harness.corpus import Corpus
from evaluation.harness.gold import GOLD_DIR, GoldCase
from services.citation_verifier import despace, extract_citations
from utils.text_match import compact, spaced_ocr_ratio

RETRIEVAL_PATH = GOLD_DIR / "retrieval.v1.jsonl"


class RetrievalCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    id: str
    query: str = Field(min_length=8)
    stratum: Literal["positivo", "limite", "negativo"]
    split: Literal["dev", "holdout"]
    status: Literal["candidate", "reviewed", "adjudicated"]
    must_abstain: bool
    relevant: list[str]
    supporting: list[str]
    jurisprudence: list[str]


def _text_citations(text):
    found = extract_citations(text)
    if spaced_ocr_ratio(text) > 0.5:
        found += extract_citations(despace(text))
    return found


def is_jurisprudence(segment, corpus: Corpus) -> bool:
    if any(c.kind == "casacion" for c in _text_citations(segment.text)):
        return True
    head = " ".join(s.text for s in corpus.documents[segment.doc_id].segments[:5])
    return "casacion" in compact(head)


def derive(cases, corpus: Corpus) -> list:
    out = []
    for case in sorted(cases, key=lambda c: c.id):
        relevant = sorted({f.source.segment_id for f in case.required_facts})
        supporting = sorted({r.segment_id for r in case.reference_segments} - set(relevant))
        jurisprudence = [sid for sid in relevant + supporting if is_jurisprudence(corpus.segments[sid], corpus)]
        out.append(
            RetrievalCase(
                id=case.id, query=case.query, stratum=case.stratum, split=case.split, status=case.status,
                must_abstain=case.must_abstain, relevant=relevant, supporting=supporting, jurisprudence=jurisprudence,
            )
        )
    return out


def dump(cases, path=RETRIEVAL_PATH):
    lines = [json.dumps(c.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) for c in cases]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def load(path=RETRIEVAL_PATH) -> list:
    return [RetrievalCase.model_validate_json(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def build_from_legal_qa(corpus=None):
    from evaluation.harness.gold import load_gold

    corpus = corpus or Corpus.load()
    return derive(load_gold(corpus=corpus), corpus)


if __name__ == "__main__":
    built = build_from_legal_qa()
    dump(built)
    print(f"{len(built)} casos de recuperación escritos en {RETRIEVAL_PATH}")
