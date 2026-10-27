"""Corrección editorial candidata sin alterar PDF/Markdown ni aprobar derecho."""

from copy import deepcopy

import pytest

from ingestion.legal_structure import parse_legal_structure
from ingestion.sat_graph.__main__ import main as cli
from ingestion.sat_graph.store import SATGraphStore, digest
from tests.backend.unit.test_legal_structure import assert_exact, make_evidence


def review_for(text, heading):
    start = text.index(heading)
    return {
        "markdown_sha256": digest(text),
        "reviewer_kind": "ai_documentary",
        "reviewer": "test-documentary-review",
        "reviewed_at": "2026-10-11T00:00:00+00:00",
        "instrument_boundaries": [
            {
                "start": start,
                "end": start + len(heading),
                "text_sha256": digest(heading),
                "reason": "Título del anexo fusionado con firma; fixture, no texto legal.",
            }
        ],
    }


def test_documentary_boundary_separates_merged_tuo_without_rewriting_evidence():
    heading = "TEXTO ÚNICO ORDENADO DE LA LEY Nº 90001"
    text = f"DECRETO SUPREMO Nº 001-2099-JUS\r\nArtículo 1.- Aprobación\r\nFirma 🔎 {heading}\r\nTÍTULO I\r\nArtículo 1.- Objeto\r\n"
    review = review_for(text, heading)
    before = deepcopy(review)
    original = parse_legal_structure(text)
    parsed = parse_legal_structure(text, documentary_review=review)
    assert_exact(text, parsed)
    assert review == before
    instruments = [n for n in parsed["nodes"] if n["kind"] == "instrument"]
    assert len(instruments) == 2
    assert instruments[0]["end"] == instruments[1]["start"] == text.index(heading)
    articles = [n for n in parsed["nodes"] if n["kind"] == "article"]
    assert articles[0]["parent_id"] == instruments[0]["id"]
    title = next(n for n in parsed["nodes"] if n["kind"] == "titulo")
    assert title["parent_id"] == instruments[1]["id"]
    assert articles[1]["parent_id"] == title["id"]
    assert original["documentary_review"] is None
    assert parsed["documentary_review"]["reviewer_kind"] == "ai_documentary"


@pytest.mark.parametrize(
    "defect",
    ["stale", "hash", "range", "duplicate", "empty_reason", "timezone", "authority"],
)
def test_documentary_boundary_rejects_stale_or_invalid_corrections(defect):
    text = "LEY 90001\nArtículo 1.- Host\nANEXO CANDIDATO\nArtículo 1.- Anexo"
    review = review_for(text, "ANEXO CANDIDATO")
    b = review["instrument_boundaries"][0]
    if defect == "stale":
        review["markdown_sha256"] = "0" * 64
    elif defect == "hash":
        b["text_sha256"] = "0" * 64
    elif defect == "range":
        b["end"] = len(text) + 1
    elif defect == "duplicate":
        review["instrument_boundaries"].append(deepcopy(b))
    elif defect == "empty_reason":
        b["reason"] = " "
    elif defect == "timezone":
        review["reviewed_at"] = "2026-10-11T00:00:00"
    else:
        review["valid_from"] = "2026-01-01"
    with pytest.raises(ValueError):
        parse_legal_structure(text, documentary_review=review)


@pytest.mark.parametrize("wrapper", ["«{}»", "> {}", "```\n{}\n```"])
def test_documentary_boundary_cannot_turn_protected_payload_into_instrument(wrapper):
    heading = "LEY 90002"
    text = "LEY 90001\nArtículo 1.- Host\n" + wrapper.format(heading)
    with pytest.raises(ValueError, match="cita o código"):
        parse_legal_structure(text, documentary_review=review_for(text, heading))


def test_documentary_review_persists_separate_parse_without_promotion(tmp_path):
    text = "LEY 90001\nArtículo 1.- Host\nFirma ANEXO CANDIDATO\nArtículo 1.- Anexo"
    evidence = make_evidence(tmp_path, text)
    store = SATGraphStore(tmp_path / "sat.db")
    original = store.stage(evidence, text)
    corrected = store.stage(
        evidence, text, documentary_review=review_for(text, "ANEXO CANDIDATO")
    )
    assert original["parse_id"] != corrected["parse_id"]
    assert corrected["review_state"] == "pending_review"
    assert store.export()["reviewed_version_count"] == 0
    assert (
        store.structure(evidence.evidence_id, original["parse_id"])["structure"][
            "documentary_review"
        ]
        is None
    )
    with pytest.raises(ValueError, match="Múltiples"):
        store.structure(evidence.evidence_id)


def test_documentary_review_cli_preserves_sidecar_and_source_bytes(tmp_path, capsys):
    import json

    text = "LEY 90001\nArtículo 1.- Host\nFirma ANEXO CANDIDATO\nArtículo 1.- Anexo"
    make_evidence(tmp_path, text)
    review = review_for(text, "ANEXO CANDIDATO")
    path = tmp_path / "review.json"
    path.write_text(json.dumps(review), encoding="utf-8")
    result = cli(
        [
            "--db",
            str(tmp_path / "sat.db"),
            "stage",
            "--pdf",
            str(tmp_path / "fixture.pdf"),
            "--markdown",
            str(tmp_path / "fixture.md"),
            "--documentary-review",
            str(path),
        ]
    )
    saved = SATGraphStore(tmp_path / "sat.db").structure(
        result["evidence_id"], result["parse_id"]
    )
    assert saved["structure"]["documentary_review"]["reviewer"] == review["reviewer"]
    assert (tmp_path / "fixture.md").read_bytes() == text.encode()
    assert result["review_state"] == "pending_review"
    capsys.readouterr()
