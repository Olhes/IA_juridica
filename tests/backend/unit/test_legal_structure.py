"""Estructura candidata con fixtures ficticios; no evalúa vigencia peruana."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ingestion.conversion import ConversionArtifact, convert_for_ingestion
from ingestion.docling_processor import LegalPDFProcessor
from ingestion.legal_structure import align_docling, parse_legal_structure
from ingestion.sat_graph.__main__ import main as cli
from ingestion.sat_graph.store import SATGraphStore, digest
from ingestion.source_evidence import persist_source_evidence


def assert_exact(text, parsed):
    by_id = {n["id"]: n for n in parsed["nodes"]}
    segments = parsed["segments"]
    assert "".join(text[s["start"] : s["end"]] for s in segments) == text
    assert all(
        left["end"] == right["start"] for left, right in zip(segments, segments[1:])
    )
    for item in [*segments, *parsed["nodes"]]:
        assert item["text_sha256"] == digest(text[item["start"] : item["end"]])
    for n in parsed["nodes"]:
        assert n["review_required"] and n["provenance_state"] == "unverified"
        if n["parent_id"]:
            parent = by_id[n["parent_id"]]
            assert parent["start"] <= n["start"] <= n["end"] <= parent["end"]
            assert n["depth"] == parent["depth"] + 1
    assert not any(k in parsed for k in ("valid_from", "checked_through", "reviewer"))


@pytest.mark.parametrize(
    "text",
    [
        "",
        "  \r\n",
        "Preámbulo 🔎\r\nArtí culo roto\n",
        "Arti\u0301culo único.- Regla 🔎\r\nSin normalizar á\r\n",
    ],
)
def test_legal_parser_preserves_exact_unicode_partition(text):
    parsed = parse_legal_structure(text)
    assert_exact(text, parsed)
    assert parsed == parse_legal_structure(text)


def test_legal_parser_uses_legal_hierarchy_not_markdown_depth():
    text = "# LEY Nº 90001\n###### TÍTULO I\n# CAPÍTULO II\nArtículo 1.- Regla\n1. Deber\n1.1. Detalle\na) Opción\nii) Subdetalle\nArtículo 2-A.- Otra\n"
    parsed = parse_legal_structure(text)
    assert_exact(text, parsed)
    nodes = parsed["nodes"]
    assert [n["kind"] for n in nodes] == [
        "document",
        "instrument",
        "titulo",
        "capitulo",
        "article",
        "numeral",
        "numeral",
        "inciso",
        "subinciso",
        "article",
    ]
    assert nodes[-1]["parent_id"] == nodes[3]["id"]
    assert nodes[-1]["number"] == "2-a"
    assert nodes[6]["parent_id"] == nodes[5]["id"]


def test_legal_parser_separates_instruments_and_contextual_lists():
    text = "1. Esto no es numeral jurídico\na) Tampoco\nLEY 90001\nArt. 149-A.- Ficticio\n1.1 Detalle\n2.1 Otro prefijo\nDECRETO SUPREMO Nº 004-2099-JUS\nArtículo Único.- Ficticio\n"
    parsed = parse_legal_structure(text)
    assert_exact(text, parsed)
    instruments = [n for n in parsed["nodes"] if n["kind"] == "instrument"]
    assert len(instruments) == 2
    assert instruments[0]["end"] == instruments[1]["start"]
    articles = [n for n in parsed["nodes"] if n["kind"] == "article"]
    assert [n["parent_id"] for n in articles] == [n["id"] for n in instruments]
    numerals = [n for n in parsed["nodes"] if n["kind"] == "numeral"]
    assert len(numerals) == 2 and all(
        n["parent_id"] == articles[0]["id"] for n in numerals
    )
    assert any(d["code"] == "missing_numeral_parent" for d in parsed["diagnostics"])


def test_legal_parser_detects_grouped_and_single_dispositions():
    text = "LEY 90001\nArtículo 1.- Texto\nDISPOSICIONES COMPLEMENTARIAS FINALES\nPRIMERA.- Ficticia\n1. Detalle\nSEGUNDA.- Ficticia\nDISPOSICIÓN COMPLEMENTARIA TRANSITORIA ÚNICA.- Ficticia\n"
    parsed = parse_legal_structure(text)
    assert_exact(text, parsed)
    dispositions = [n for n in parsed["nodes"] if n["kind"] == "disposition"]
    assert [n["number"] for n in dispositions] == ["primera", "segunda", "unica"]
    assert not any(
        n["kind"] == "article"
        for n in parsed["nodes"]
        if n["start"] > dispositions[0]["start"]
    )


def test_legal_parser_isolates_quotes_fences_tables_and_toc():
    text = "Artículo 1.- Modifícase en los siguientes términos:\n«Artículo 149.- Texto citado\nArtículo 150.- Más texto»\nArtículo 2.- Host\n> Artículo 99.- Cita\n> Continúa\n```text\nArtículo 88.- Código\n```\n| Artículo 77 | Tabla |\nArtículo 66 .... 12\n"
    parsed = parse_legal_structure(text)
    assert_exact(text, parsed)
    assert [n["number"] for n in parsed["nodes"] if n["kind"] == "article"] == [
        "1",
        "2",
    ]
    assert len([n for n in parsed["nodes"] if n["kind"] == "quoted_payload"]) == 2
    assert not any(n["kind"] == "amendment_payload" for n in parsed["nodes"])
    assert {"toc_entry_skipped", "table_requires_layout_review"} <= {
        d["code"] for d in parsed["diagnostics"]
    }


@pytest.mark.parametrize("quote", ['"', "“", "«"])
def test_legal_parser_keeps_unclosed_quotes_non_authoritative(quote):
    text = f"Artículo 1.- Host\n{quote}Artículo 149.- Reforma\nArtículo 2.- Límite incierto"
    parsed = parse_legal_structure(text)
    assert_exact(text, parsed)
    assert [n["number"] for n in parsed["nodes"] if n["kind"] == "article"] == ["1"]
    assert any(d["code"] == "unclosed_quotation" for d in parsed["diagnostics"])


def test_legal_parser_flags_unquoted_amendment_and_duplicate_headers():
    text = "LEY 90001\nLEY 90001\nArtículo 1.- Host\nArtículo 1.- Repetido\nModifícase el artículo en los siguientes términos:\nArtículo 149.- Reforma sin comillas\nArtículo 2.- No se puede adjudicar automáticamente\nTÍTULO II\nArtículo 3.- Host\n"
    parsed = parse_legal_structure(text)
    assert_exact(text, parsed)
    codes = {d["code"] for d in parsed["diagnostics"]}
    assert {
        "duplicate_heading",
        "repeated_instrument_heading",
        "unquoted_amendment_boundary_ambiguous",
    } <= codes
    assert [
        n["number"] for n in parsed["nodes"] if n["kind"] == "amendment_payload"
    ] == ["149", "2"]
    assert [n["number"] for n in parsed["nodes"] if n["kind"] == "article"] == [
        "1",
        "1",
        "3",
    ]


def test_legal_parser_does_not_truncate_after_fifty_articles():
    text = "".join(f"Artículo {i}.- Ficticio\n" for i in range(1, 151))
    parsed = parse_legal_structure(text)
    assert_exact(text, parsed)
    assert len([n for n in parsed["nodes"] if n["kind"] == "article"]) == 150
    processor = LegalPDFProcessor.__new__(LegalPDFProcessor)
    assert (
        len(
            processor._extract_legal_structure(
                SimpleNamespace(export_to_markdown=lambda: text)
            )["articles"]
        )
        == 150
    )


def test_docling_alignment_requires_unique_exact_text_and_keeps_local_provenance():
    text = "# Único 🔎\nRepetido\nRepetido\nEscapado \\*x\\*\n"
    prov = [
        {
            "page_no": 8,
            "bbox": {"l": 1, "t": 3, "r": 5, "b": 7, "coord_origin": "TOPLEFT"},
            "charspan": [0, 7],
        }
    ]
    document = {
        "texts": [
            {"self_ref": "#/texts/0", "text": "Único 🔎", "prov": prov},
            {"text": "Repetido"},
            {"text": "Escapado *x*"},
        ]
    }
    before = deepcopy(document)
    mappings, diagnostics = align_docling(text, document)
    assert [m["status"] for m in mappings] == ["unique", "ambiguous", "unmapped"]
    assert mappings[0]["start"] == 2 and mappings[0]["end"] == 9
    assert (
        mappings[0]["prov"] == prov
        and mappings[0]["prov_charspan_space"] == "docling_item_text"
    )
    assert all("start" not in m for m in mappings[1:])
    assert len(diagnostics) == 2 and document == before
    assert all(
        m["status"] == "ambiguous"
        for m in align_docling(
            "Una vez", {"texts": [{"text": "Una vez"}, {"text": "Una vez"}]}
        )[0]
    )


@pytest.mark.parametrize(
    "document", [[], {"texts": {}}, {"texts": [], "bad": float("nan")}]
)
def test_docling_alignment_rejects_invalid_json_contract(document):
    with pytest.raises(ValueError):
        parse_legal_structure("Artículo 1", document)


def make_evidence(tmp_path, text):
    pdf, md = tmp_path / "fixture.pdf", tmp_path / "fixture.md"
    pdf.write_bytes(b"%PDF-1.7\nsynthetic")
    md.write_bytes(text.encode("utf-8"))
    return persist_source_evidence(pdf, md, text, tmp_path / "evidence")


def test_sat_structure_is_immutable_concurrent_and_not_reviewed(tmp_path):
    text = "LEY 90001\nArtículo 1.- Ficticio\n"
    layout = {
        "version": "fixture-only",
        "texts": [{"text": "Ficticio", "prov": []}],
        "tables": [{"untouched": True}],
    }
    evidence = make_evidence(tmp_path, text)
    path = tmp_path / "sat.db"
    store = SATGraphStore(path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda _: SATGraphStore(path).stage(evidence, text, layout), range(8)
            )
        )
    assert len({r["parse_id"] for r in results}) == 1
    saved = store.structure(evidence.evidence_id)
    assert saved["docling_document"] == layout
    layout["texts"][0]["text"] = "Changed"
    assert store.structure(evidence.evidence_id) == saved
    graph = store.export()
    identities = {n["id"] for n in graph["nodes"]}
    assert all(
        e["source"] in identities and e["target"] in identities for e in graph["edges"]
    )
    assert graph["reviewed_version_count"] == 0
    assert all(
        n["review_required"]
        for n in graph["nodes"]
        if n["type"] in {"CandidateParse", "CandidateComponent"}
    )
    assert store.resolve("pe:ley:30364", "art-1", "2026-10-10")["state"] == "abstain"


def test_sat_structure_requires_explicit_parse_on_ambiguity_and_detects_tampering(
    tmp_path,
):
    text = "Artículo 1.- Ficticio"
    evidence = make_evidence(tmp_path, text)
    store = SATGraphStore(tmp_path / "sat.db")
    first = store.stage(evidence, text)
    second = store.stage(evidence, text, {"texts": []})
    assert first["parse_id"] != second["parse_id"]
    with pytest.raises(ValueError, match="Múltiples"):
        store.structure(evidence.evidence_id)
    assert store.structure(evidence.evidence_id, second["parse_id"])[
        "docling_document"
    ] == {"texts": []}
    with pytest.raises(ValueError, match="inexistente"):
        store.structure(evidence.evidence_id, "wrong")
    with sqlite3.connect(store.path) as db:
        db.execute(
            "UPDATE sat_parses SET artifact='{}' WHERE id=?", (first["parse_id"],)
        )
    with pytest.raises(ValueError, match="alterado"):
        store.structure(evidence.evidence_id, first["parse_id"])


def test_sat_invalid_layout_writes_no_partial_candidate_graph(tmp_path):
    text = "Artículo 1.- Ficticio"
    evidence = make_evidence(tmp_path, text)
    store = SATGraphStore(tmp_path / "sat.db")
    before = store.export()
    with pytest.raises(ValueError):
        store.stage(evidence, text, {"texts": "invalid"})
    assert store.export() == before


def test_sat_structure_cli_round_trips_docling_json(tmp_path, capsys):
    text = "Artículo único.- Ficticio"
    make_evidence(tmp_path, text)
    layout = {
        "texts": [{"text": "Ficticio", "prov": [{"page_no": 1, "charspan": [0, 8]}]}]
    }
    json_path = tmp_path / "docling.json"
    json_path.write_text(json.dumps(layout), encoding="utf-8")
    base = ["--db", str(tmp_path / "sat.db")]
    result = cli(
        [
            *base,
            "stage",
            "--pdf",
            str(tmp_path / "fixture.pdf"),
            "--markdown",
            str(tmp_path / "fixture.md"),
            "--docling-json",
            str(json_path),
        ]
    )
    output = tmp_path / "structure.json"
    parsed = cli(
        [
            *base,
            "--output",
            str(output),
            "structure",
            "--evidence-id",
            result["evidence_id"],
            "--parse-id",
            result["parse_id"],
        ]
    )
    assert json.loads(output.read_text(encoding="utf-8")) == parsed
    assert parsed["docling_document"] == layout
    assert len(capsys.readouterr().out.splitlines()) == 2


def test_docling_artifact_converts_once_without_output_side_effects(tmp_path):
    pdf = tmp_path / "fixture.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    calls = []
    document = SimpleNamespace(
        export_to_markdown=lambda: "Artículo 1.- Texto",
        export_to_dict=lambda **_: {"texts": []},
    )
    processor = LegalPDFProcessor.__new__(LegalPDFProcessor)
    processor.converter = SimpleNamespace(
        convert=lambda path: calls.append(path) or SimpleNamespace(document=document)
    )
    artifact = asyncio.run(convert_for_ingestion(processor, str(pdf)))
    assert artifact == ConversionArtifact("Artículo 1.- Texto", {"texts": []})
    assert calls == [pdf] and not (tmp_path / "fixture.md").exists()
    with pytest.raises(FileNotFoundError):
        asyncio.run(processor.process_pdf_artifact(str(tmp_path / "missing.pdf")))


def test_conversion_adapter_supports_legacy_processors_without_inventing_layout():
    processor = AsyncMock()
    processor.process_pdf.return_value = "Artículo único"
    artifact = asyncio.run(convert_for_ingestion(processor, "fixture.pdf"))
    assert artifact == ConversionArtifact("Artículo único")
    processor.process_pdf.assert_awaited_once_with("fixture.pdf", write_output=False)
    bad = SimpleNamespace(
        process_pdf_artifact=AsyncMock(return_value={"markdown": "not the contract"})
    )
    with pytest.raises(ValueError, match="Contrato"):
        asyncio.run(convert_for_ingestion(bad, "fixture.pdf"))
