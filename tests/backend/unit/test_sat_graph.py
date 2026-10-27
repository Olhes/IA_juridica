"""Contratos SAT offline; textos/datos inventados, no validación del derecho peruano."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json

import pytest
from pydantic import ValidationError

from ingestion.sat_graph.__main__ import main
from ingestion.sat_graph.catalog import CATALOG_PATH, load_catalog
from ingestion.sat_graph.contracts import ReviewManifest, ReviewedUnit
from ingestion.sat_graph.store import SATGraphStore, candidate_spans, digest, version_id
from ingestion.source_evidence import persist_source_evidence

RESOURCE = "pe:ley:30364"


def staged(tmp_path, store, content, key="one"):
    pdf, md = tmp_path / f"{key}.pdf", tmp_path / f"{key}.md"
    pdf.write_bytes(b"%PDF-1.7\n" + key.encode())
    md.write_bytes(content.encode("utf-8"))
    evidence = persist_source_evidence(pdf, md, content, tmp_path / "source_evidence")
    store.stage(evidence, content)
    return evidence


def unit(content, component="art-1", **overrides):
    return {
        "resource_id": RESOURCE,
        "component": component,
        "label": component,
        "start": 0,
        "end": len(content),
        "text_sha256": digest(content),
        "valid_from": "2020-01-01",
        **overrides,
    }


def review(evidence, units, **overrides):
    return ReviewManifest.model_validate(
        {
            "evidence_id": evidence.evidence_id,
            "source_resource_id": RESOURCE,
            "pdf_sha256": evidence.pdf_sha256,
            "markdown_sha256": evidence.markdown_sha256,
            "reviewer": "Revisor de fixture, no autoridad real",
            "reviewed_at": "2026-10-07T12:00:00-05:00",
            "checked_through": "2026-10-07",
            "effective_date_basis": "Fecha inventada exclusivamente para prueba",
            "units": units,
            **overrides,
        }
    )


def test_sat_catalog_is_official_scoped_and_not_authoritative(tmp_path):
    resources = load_catalog()
    assert {topic for item in resources for topic in item["topics"]} == {
        "violencia",
        "alimentos",
    }
    store = SATGraphStore(tmp_path / "sat.db")
    graph = store.export()
    assert graph["resource_count"] == len(resources) >= 21
    assert graph["reviewed_version_count"] == 0
    assert all(
        n["state"] == "catalogued" and not n["content_ingested"]
        for n in graph["nodes"]
        if n["type"] == "Resource"
    )
    assert store.resolve(RESOURCE, "art-1", "2026-10-07")["state"] == "abstain"


@pytest.mark.parametrize("change", ["duplicate", "external", "http", "version"])
def test_sat_catalog_rejects_unsafe_or_ambiguous_entries(tmp_path, change):
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if change == "duplicate":
        data["resources"].append(data["resources"][0])
    elif change == "external":
        data["resources"][0]["url"] = "https://gob.pe.example.com/law"
    elif change == "http":
        data["resources"][0]["url"] = "http://www.gob.pe/law"
    else:
        data["schema_version"] = 99
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        load_catalog(path)


def test_sat_article_spans_preserve_exact_unicode_without_overlap():
    content = (
        "# Preámbulo\n\nArtículo 1.- título\n"
        + "á🔎" * 2000
        + "\n#### Artículo 2-A. Otra regla\nFin\n"
    )
    spans = candidate_spans(content)
    assert len(spans) == 3
    assert "".join(content[s["start"] : s["end"]] for s in spans) == content
    assert all(
        s["text_sha256"] == digest(content[s["start"] : s["end"]]) for s in spans
    )
    assert len(candidate_spans("Texto sin artículos")) == 1


def test_sat_stage_is_idempotent_concurrent_and_survives_restart(tmp_path):
    path = tmp_path / "sat.db"
    store = SATGraphStore(path)
    content = "Artículo único\nTexto ficticio."
    evidence = staged(tmp_path, store, content)
    initial = store.export()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(lambda _: SATGraphStore(path).stage(evidence, content), range(8))
        )
    assert all(
        r["review_state"] == "pending_review" and r["llm_calls"] == 0 for r in results
    )
    assert SATGraphStore(path).export() == initial
    assert not any(
        n["type"] in {"Work", "CTV", "CLV", "Action"} for n in initial["nodes"]
    )


def test_sat_stage_rejects_divergent_hash_or_identity(tmp_path):
    store = SATGraphStore(tmp_path / "sat.db")
    evidence = staged(tmp_path, store, "Uno")
    before = store.export()
    for bad, text in [
        (evidence, "Otro"),
        (replace(evidence, evidence_id="wrong"), "Uno"),
        (replace(evidence, provenance_state="reviewed"), "Uno"),
    ]:
        with pytest.raises(ValueError):
            store.stage(bad, text)
    assert store.export() == before


def test_sat_review_resolves_half_open_intervals_and_abstains(tmp_path):
    store = SATGraphStore(tmp_path / "sat.db")
    content = "Regla inventada."
    evidence = staged(tmp_path, store, content)
    manifest = review(evidence, [unit(content, valid_to="2025-01-01")])
    result = store.review(manifest)
    assert store.review(manifest) == result
    assert (
        SATGraphStore(store.path).resolve(RESOURCE, "art-1", "2020-01-01")["state"]
        == "resolved"
    )
    assert store.resolve(RESOURCE, "art-1", "2024-12-31")["text"]["text"] == content
    for when in ("2019-12-31", "2025-01-01"):
        assert store.resolve(RESOURCE, "art-1", when)["state"] == "abstain"
    assert (
        store.resolve(RESOURCE, "art-1", "2024-01-01", language="qu")["state"]
        == "abstain"
    )
    assert (
        store.resolve(RESOURCE, "art-1", "2024-01-01", scope="OTHER")["state"]
        == "abstain"
    )
    with pytest.raises(ValueError):
        store.resolve(RESOURCE, "art-1", "20241007")
    assert store.export()["documents"][0]["state"] == "reviewed"
    assert all(
        "reviewer" in edge["evidence"]
        for edge in store.export()["edges"]
        if edge["type"] == "has_text"
    )


def test_sat_review_never_extrapolates_past_verified_coverage(tmp_path):
    store = SATGraphStore(tmp_path / "sat.db")
    evidence = staged(tmp_path, store, "Regla abierta.")
    store.review(review(evidence, [unit("Regla abierta.")]))
    assert (
        store.resolve(RESOURCE, "art-1", "2026-10-08")["reason"]
        == "outside_reviewed_coverage"
    )


@pytest.mark.parametrize("change", ["hash", "span", "source", "duplicate", "overlap"])
def test_sat_review_rejects_bad_evidence_without_partial_writes(tmp_path, change):
    store = SATGraphStore(tmp_path / "sat.db")
    content = "Regla A"
    evidence = staged(tmp_path, store, content)
    units, overrides = [unit(content)], {}
    if change == "hash":
        overrides["pdf_sha256"] = "0" * 64
    elif change == "span":
        units[0]["end"] = 1000
    elif change == "source":
        overrides["source_resource_id"] = "pe:service:linea-100"
    elif change == "duplicate":
        units.append(units[0])
    else:
        units.append(unit(content, valid_from="2021-01-01"))
    before = store.export()
    with pytest.raises(ValueError):
        store.review(review(evidence, units, **overrides))
    assert store.export() == before


@pytest.mark.parametrize(
    "overrides",
    [
        {"reviewer": " "},
        {"reviewed_at": "2026-10-07T12:00:00"},
        {"checked_through": "2026-10-08"},
        {"effective_date_basis": ""},
        {"invented_flag": True},
    ],
)
def test_sat_review_contract_requires_explicit_human_review(tmp_path, overrides):
    store = SATGraphStore(tmp_path / "sat.db")
    evidence = staged(tmp_path, store, "Regla")
    with pytest.raises(ValidationError):
        review(evidence, [unit("Regla")], **overrides)


def amendment(evidence, content, old_id, **overrides):
    new_unit = unit(content, valid_from="2025-01-01")
    action = {
        "action_key": "modifica-art-1",
        "kind": "amend",
        "effective_on": "2025-01-01",
        "start": 0,
        "end": len(content),
        "text_sha256": digest(content),
        "terminates": [old_id],
        "produces": [version_id(ReviewedUnit.model_validate(new_unit))],
        **overrides,
    }
    return review(evidence, [new_unit], actions=[action])


def test_sat_amendment_closes_old_version_with_causal_evidence(tmp_path):
    store = SATGraphStore(tmp_path / "sat.db")
    old = staged(tmp_path, store, "Vieja", "old")
    old_id = store.review(review(old, [unit("Vieja")]))["version_ids"][0]
    new = staged(tmp_path, store, "Nueva", "new")
    manifest = amendment(new, "Nueva", old_id)
    result = store.review(manifest)
    assert store.review(manifest) == result
    assert store.resolve(RESOURCE, "art-1", "2024-12-31")["text"]["text"] == "Vieja"
    assert store.resolve(RESOURCE, "art-1", "2025-01-01")["text"]["text"] == "Nueva"
    causal = [
        e
        for e in store.export()["edges"]
        if e["type"] in {"terminates", "produces", "source"}
    ]
    assert {e["type"] for e in causal} == {"terminates", "produces", "source"}
    assert all(e["evidence"]["evidence_id"] == new.evidence_id for e in causal)


@pytest.mark.parametrize(
    "overrides",
    [
        {"effective_on": "2019-01-01"},
        {"effective_on": "2024-01-01"},
        {"terminates": ["missing"]},
        {"produces": []},
        {"text_sha256": "0" * 64},
        {"kind": "repeal"},
        {"kind": "enact"},
    ],
)
def test_sat_invalid_action_rolls_back_versions_and_closures(tmp_path, overrides):
    store = SATGraphStore(tmp_path / "sat.db")
    old = staged(tmp_path, store, "Vieja", "old")
    old_id = store.review(review(old, [unit("Vieja")]))["version_ids"][0]
    new = staged(tmp_path, store, "Nueva", "new")
    before = store.export()
    with pytest.raises(ValueError):
        store.review(amendment(new, "Nueva", old_id, **overrides))
    assert store.export() == before


def test_sat_structure_supports_explicit_unchanged_child_reuse(tmp_path):
    store = SATGraphStore(tmp_path / "sat.db")
    content = "Estructura ficticia."
    evidence = staged(tmp_path, store, content)
    units = [
        unit(content, "root", valid_to="2025-01-01"),
        unit(content, "root", valid_from="2025-01-01"),
        unit(content, "art-1", parent_component="root"),
    ]
    ids = [version_id(ReviewedUnit.model_validate(u)) for u in units]
    memberships = [{"parent_version": p, "child_version": ids[2]} for p in ids[:2]]
    store.review(review(evidence, units, memberships=memberships))
    edges = [e for e in store.export()["edges"] if e["type"] == "contains_version"]
    assert len(edges) == 2 and {e["target"] for e in edges} == {ids[2]}


@pytest.mark.parametrize("defect", ["self", "missing", "coverage"])
def test_sat_structure_rejects_invalid_parent_and_membership(tmp_path, defect):
    store = SATGraphStore(tmp_path / "sat.db")
    content = "Estructura ficticia."
    evidence = staged(tmp_path, store, content)
    units = [unit(content, "root"), unit(content, "art-1", parent_component="root")]
    if defect == "self":
        units[0]["parent_component"] = "root"
    if defect == "missing":
        units[1]["parent_component"] = "absent"
    if defect == "coverage":
        units[1]["valid_from"] = "2021-01-01"
    ids = [version_id(ReviewedUnit.model_validate(u)) for u in units]
    before = store.export()
    with pytest.raises(ValueError):
        store.review(
            review(
                evidence,
                units,
                memberships=[{"parent_version": ids[0], "child_version": ids[1]}],
            )
        )
    assert store.export() == before


def test_sat_cli_draft_cannot_be_promoted_without_review(tmp_path, capsys):
    path = tmp_path / "sat.db"
    store = SATGraphStore(path)
    evidence = staged(tmp_path, store, "Artículo 1. Ficticio")
    draft = main(
        [
            "--db",
            str(path),
            "draft",
            "--evidence-id",
            evidence.evidence_id,
            "--resource-id",
            RESOURCE,
        ]
    )
    assert draft["units"][0]["valid_from"] is None
    with pytest.raises(ValidationError):
        ReviewManifest.model_validate(draft)
    assert json.loads(capsys.readouterr().out)["evidence_id"] == evidence.evidence_id
    assert main(["--db", str(path), "export"])["reviewed_version_count"] == 0


def test_sat_enactment_and_pure_repeal_preserve_audit(tmp_path):
    store = SATGraphStore(tmp_path / "sat.db")
    content = "Regla promulgada ficticia"
    evidence = staged(tmp_path, store, content)
    reviewed_unit = unit(content)
    vid = version_id(ReviewedUnit.model_validate(reviewed_unit))
    action = {
        "action_key": "enact-1",
        "kind": "enact",
        "effective_on": "2020-01-01",
        "start": 0,
        "end": len(content),
        "text_sha256": digest(content),
        "produces": [vid],
    }
    store.review(review(evidence, [reviewed_unit], actions=[action]))
    repeal_text = "Se deroga la regla ficticia"
    repealer = staged(tmp_path, store, repeal_text, "repeal")
    repeal = {
        "action_key": "repeal-1",
        "kind": "repeal",
        "effective_on": "2025-01-01",
        "start": 0,
        "end": len(repeal_text),
        "text_sha256": digest(repeal_text),
        "terminates": [vid],
    }
    result = store.review(review(repealer, [], actions=[repeal]))
    assert result["version_ids"] == []
    assert store.resolve(RESOURCE, "art-1", "2024-12-31")["state"] == "resolved"
    assert store.resolve(RESOURCE, "art-1", "2025-01-01")["state"] == "abstain"
    assert len([n for n in store.export()["nodes"] if n["type"] == "Action"]) == 2


def test_sat_closing_child_requires_consistent_existing_parent_version(tmp_path):
    store = SATGraphStore(tmp_path / "sat.db")
    content = "Estructura ficticia"
    evidence = staged(tmp_path, store, content)
    units = [unit(content, "root"), unit(content, parent_component="root")]
    parent_id, old_id = [version_id(ReviewedUnit.model_validate(u)) for u in units]
    store.review(
        review(
            evidence,
            units,
            memberships=[{"parent_version": parent_id, "child_version": old_id}],
        )
    )
    new = staged(tmp_path, store, "Nueva", "new")
    before = store.export()
    with pytest.raises(ValueError, match="hija no cubre"):
        store.review(amendment(new, "Nueva", old_id))
    assert store.export() == before


def test_sat_rejects_multinode_structural_cycles(tmp_path):
    store = SATGraphStore(tmp_path / "sat.db")
    evidence = staged(tmp_path, store, "Original")
    store.review(review(evidence, [unit("Original", "a")]))
    evidence2 = staged(tmp_path, store, "Nuevo", "new")
    units = [
        unit("Nuevo", "b", parent_component="a"),
        unit("Nuevo", "a", parent_component="b", valid_from="2025-01-01"),
    ]
    new_id = version_id(ReviewedUnit.model_validate(units[1]))
    old_id = store.resolve(RESOURCE, "a", "2024-01-01")["version_id"]
    action = {
        "action_key": "change-a",
        "kind": "amend",
        "effective_on": "2025-01-01",
        "start": 0,
        "end": 5,
        "text_sha256": digest("Nuevo"),
        "terminates": [old_id],
        "produces": [new_id],
    }
    before = store.export()
    with pytest.raises(ValueError, match="Ciclo"):
        store.review(review(evidence2, units, actions=[action]))
    assert store.export() == before


def test_sat_cli_writes_utf8_without_overwriting_review_files(tmp_path):
    output, db = tmp_path / "export.json", tmp_path / "sat.db"
    args = ["--db", str(db), "--output", str(output), "export"]
    result = main(args)
    assert json.loads(output.read_bytes().decode("utf-8")) == result
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        main(args)
    assert output.read_bytes() == before
