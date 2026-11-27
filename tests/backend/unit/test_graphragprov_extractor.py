"""Unit tests for deterministic and optional Cohere extractors plus NL-to-SPARQL."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from services.graphragprov.extractor import (
    CohereGroundedExtractor,
    DeterministicLegalExtractor,
)
from services.graphragprov.nl_sparql import (
    compile_nl_to_sparql_cohere,
    compile_nl_to_sparql_deterministic,
)
from services.graphragprov.sparql import evaluate_sparql, parse_sparql


def _sample_doc_payload() -> dict:
    markdown = (
        "Ley N° 28970 — Ley que crea el REDAM\n"
        "Artículo 1. Creación y objeto\n"
        "El Poder Judicial deberá crear y administrar el Registro de Deudores Alimentarios Morosos "
        "conforme a la Ley N° 27444.\n"
        "Artículo 2. Plazos y prohibiciones\n"
        "El órgano jurisdiccional remitirá la resolución en un plazo máximo de 15 días hábiles. "
        "Se prohíbe cobrar tasas administrativas por la inscripción. "
        "Se modifica el Artículo 566 del Código Procesal Civil.\n"
    )
    a1_s = markdown.index("Artículo 1.")
    a2_s = markdown.index("Artículo 2.")
    return {
        "id": "pe:ley:28970",
        "title": "Ley N° 28970",
        "editable": True,
        "versions": [
            {"id": "v:root", "component_id": "root", "label": "Ley N° 28970", "kind": "instrument", "archived": False, "texts": [{"id": "t:root", "language": "es", "text": markdown}]},
            {"id": "v:art1", "component_id": "art1", "label": "Artículo 1", "kind": "article", "archived": False, "texts": [{"id": "t:art1", "language": "es", "text": markdown[a1_s:a2_s]}]},
            {"id": "v:art2", "component_id": "art2", "label": "Artículo 2", "kind": "article", "archived": False, "texts": [{"id": "t:art2", "language": "es", "text": markdown[a2_s:]}]},
        ],
        "edition": {
            "revision": "rev:28970-v1",
            "markdown": markdown,
            "components": [
                {"id": "root", "label": "Ley N° 28970", "kind": "instrument", "parent_id": None, "start": 0, "end": len(markdown)},
                {"id": "art1", "label": "Artículo 1", "kind": "article", "parent_id": "root", "start": a1_s, "end": a2_s},
                {"id": "art2", "label": "Artículo 2", "kind": "article", "parent_id": "root", "start": a2_s, "end": len(markdown)},
            ],
        },
    }


def test_deterministic_legal_extractor_grounds_structural_citations_and_deontic_clauses():
    doc = _sample_doc_payload()
    graph = DeterministicLegalExtractor().extract(doc)

    assert graph.doc_id == "pe:ley:28970"
    assert graph.cohere_used is False
    assert len(graph.occurrences) >= 8
    assert set(graph.source_units) == {"root", "art1", "art2"}

    pred_iris = set(graph.predicates)
    assert "http://iajuridica.pe/sat/hasComponent" in pred_iris
    assert "http://iajuridica.pe/sat/partOf" in pred_iris
    assert "http://iajuridica.pe/legal/obligates" in pred_iris
    assert "http://iajuridica.pe/legal/prohibits" in pred_iris
    assert "http://iajuridica.pe/legal/setsDeadline" in pred_iris
    assert "http://iajuridica.pe/legal/cites" in pred_iris
    assert "http://iajuridica.pe/legal/amends" in pred_iris

    # Verify every single extracted occurrence has valid doc-relative evidence spans matching markdown.
    md = doc["edition"]["markdown"]
    for occ in graph.occurrences:
        ev = occ.spans.doc_evidence_span
        assert md[ev.start : ev.end] == ev.surface_text
        if occ.spans.object_span is not None:
            ob = occ.spans.object_span
            assert md[ob.start : ob.end] == ob.surface_text

    # Every generated sample query parses and runs cleanly on the graph.
    assert len(graph.sample_queries) >= 2
    for sq in graph.sample_queries:
        res = evaluate_sparql(graph, sq.sparql)
        assert len(res.rows) >= 1


def test_deterministic_extractor_handles_non_editable_document_without_edition_markdown():
    doc = {
        "id": "pe:dl:1377",
        "title": "DL 1377",
        "editable": False,
        "edition": None,
        "revisions": ["rev:compacted"],
        "versions": [
            {
                "id": "ctv:art1",
                "component_id": "ctv:art1",
                "label": "Artículo 1",
                "kind": "article",
                "archived": False,
                "texts": [{"id": "clv:art1", "language": "es", "text": "Artículo 1. El Estado deberá proteger a las víctimas."}],
            }
        ],
    }
    graph = DeterministicLegalExtractor().extract(doc)
    assert "ctv:art1" in graph.source_units
    assert "deberá proteger" in graph.source_units["ctv:art1"].text
    assert any(occ.predicate.value.endswith("/obligates") for occ in graph.occurrences)


def test_deterministic_nl_to_sparql_compiles_legal_intents_and_executes():
    graph = DeterministicLegalExtractor().extract(_sample_doc_payload())
    for question in (
        "¿Qué obligaciones establece la ley?",
        "¿Qué prohibiciones existen?",
        "¿Cuál es el plazo máximo menor a 30 días?",
        "¿Qué normas son citadas o modificadas?",
        "Muéstrame la estructura multi-salto de los componentes",
    ):
        sparql, _warnings = compile_nl_to_sparql_deterministic(question, graph)
        parse_sparql(sparql)
        result = evaluate_sparql(graph, sparql)
        assert len(result.rows) >= 1


def test_cohere_grounded_extractor_firewall_accepts_grounded_and_rejects_hallucinated(monkeypatch):
    doc = _sample_doc_payload()
    base = DeterministicLegalExtractor().extract(doc)

    recorded_calls: list[dict] = []

    class FakeCohereChat:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key

        async def chat(self, *, message, preamble=None, chat_history=(), **options):
            recorded_calls.append({"options": options, "has_thinking_arg": "thinking" in options})
            if "Artículo 2" in message:
                payload = (
                    '```json\n'
                    '[{"subject": "órgano jurisdiccional", "predicate": "legal:obligates", '
                    '"object": "remitir la resolución", '
                    '"subject_quote": "órgano jurisdiccional", "predicate_quote": "remitirá", '
                    '"object_quote": "remitirá la resolución"},'
                    '{"subject": "Entidad Fantasma", "predicate": "legal:obligates", '
                    '"object": "pagar un bono inventado", '
                    '"subject_quote": "Entidad Fantasma", "predicate_quote": "obliga", '
                    '"object_quote": "pagar un bono inventado"}]\n'
                    '```'
                )
            else:
                payload = "[]"
            return SimpleNamespace(text=payload, finish_reason="COMPLETE")

    monkeypatch.setattr("services.cohere_chat.CohereChat", FakeCohereChat)

    extractor = CohereGroundedExtractor(api_key="test-key", model="command-a-plus-08-2025")
    merged = asyncio.run(extractor.extract(doc, base_graph=base))

    assert merged.cohere_used is True
    assert merged.unlocalized_discarded >= 1
    assert any(
        occ.origin == "cohere_llm" and occ.object.value == "remitir la resolución"
        for occ in merged.occurrences
    )
    assert not any(occ.object.value == "pagar un bono inventado" for occ in merged.occurrences)
    # Must never pass raw `thinking` option directly (CohereChat handles default_thinking_option).
    assert recorded_calls and all(not call["has_thinking_arg"] for call in recorded_calls)


def test_cohere_nl_to_sparql_validates_output(monkeypatch):
    graph = DeterministicLegalExtractor().extract(_sample_doc_payload())

    class FakeCohereChat:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key

        async def chat(self, *, message, preamble=None, chat_history=(), **options):
            return SimpleNamespace(
                text=(
                    "```sparql\n"
                    "PREFIX legal: <http://iajuridica.pe/legal/>\n"
                    "SELECT DISTINCT ?s ?o WHERE { ?s legal:prohibits ?o . }\n"
                    "```"
                ),
                finish_reason="COMPLETE",
            )

    monkeypatch.setattr("services.cohere_chat.CohereChat", FakeCohereChat)
    sparql, warnings = asyncio.run(
        compile_nl_to_sparql_cohere(
            "¿Qué está prohibido?",
            graph,
            api_key="test-key",
            model="command-r7b-12-2024",
        )
    )
    assert warnings == []
    res = evaluate_sparql(graph, sparql)
    assert len(res.rows) >= 1
