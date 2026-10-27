"""PDF y textos ficticios: contratos de investigación, no un corpus oficial real."""

import json
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256

import pytest
from docling_core.types.doc import DocItemLabel, DoclingDocument, GroupLabel
from pypdf import PdfWriter

from research.documentary import (
    DocumentaryPlan,
    DocumentaryRetriever,
    build_snapshot,
    documentary_windows,
)
from research.sat_benchmark import run, validate_dataset
from retrieval.sat import SATRetriever, SearchPlan


@pytest.fixture
def documentary_data(tmp_path):
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    pdf = tmp_path / "fixture.pdf"
    writer.write(pdf)
    document = DoclingDocument(name="fixture")
    document.add_text(
        label=DocItemLabel.TEXT, text="Regla ficticia: alimentos y constancia."
    )
    markdown = document.export_to_markdown()
    md = tmp_path / "fixture.md"
    md.write_bytes(markdown.encode())
    layout = tmp_path / "fixture.docling.json"
    layout.write_text(
        json.dumps(document.export_to_dict(mode="json")), encoding="utf-8"
    )

    def artifact(path):
        return {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()}

    source_id = "pdf-sha256-" + artifact(pdf)["sha256"]
    bundle = {
        "schema_version": 1,
        "review_kind": "ai_documentary",
        "reviewer": "test-fixture-not-real-review",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "sources": [
            {
                "id": source_id,
                "source_url": "https://www3.congreso.gob.pe/fixture-not-real.pdf",
                "pdf": artifact(pdf),
                "markdown": artifact(md),
                "docling_json": artifact(layout),
                "selected_pdf_pages": [1],
            }
        ],
        "units": [
            {
                "source_id": source_id,
                "resource_id": "pe:fixture:documentary",
                "resource_title": "Norma ficticia",
                "component": "article/1",
                "label": "Artículo ficticio",
                "start": 0,
                "end": len(markdown),
                "text_sha256": sha256(markdown.encode()).hexdigest(),
                "pdf_pages": [1],
                "reason": "Selección ficticia para probar integridad de bytes.",
            }
        ],
    }
    snapshot = build_snapshot(bundle)
    vid = next(n["id"] for n in snapshot["nodes"] if n["type"] == "DocumentaryVersion")
    return {
        "schema_version": 1,
        "kind": "official_pdf_documentary",
        "revision": "test-not-official-acquisition",
        "documentary_bundle": bundle,
        "snapshot": snapshot,
        "config": {"top_k": 1, "candidates": 5},
        "cases": [
            {
                "id": "documentary-fixture",
                "plan": {"query": "alimentos", "source_ids": [source_id]},
                "expected_version_ids": [vid],
                "reference_spans": [
                    {
                        "version_id": vid,
                        "start": 0,
                        "end": len(markdown),
                        "text_sha256": sha256(markdown.encode()).hexdigest(),
                    }
                ],
                "answerable": True,
                "stratum": "edition",
                "split": "development",
            }
        ],
    }


def test_documentary_snapshot_is_hash_bound_and_has_no_legal_versions(documentary_data):
    data = documentary_data
    validate_dataset(data)
    assert data["snapshot"] == build_snapshot(data["documentary_bundle"])
    assert not any(n["type"] == "CTV" for n in data["snapshot"]["nodes"])
    assert not any(
        n.get("provenance_state") == "reviewed" for n in data["snapshot"]["nodes"]
    )
    plan = SearchPlan(query="alimentos", as_of="2026-10-11")
    assert SATRetriever(data["snapshot"]).search(plan)["state"] == "abstain"


@pytest.mark.parametrize(
    "defect",
    [
        "nonofficial",
        "spoofed_host",
        "http",
        "id",
        "pdf_hash",
        "not_pdf",
        "md_hash",
        "rewritten_md",
        "layout_hash",
        "span_hash",
        "span_end",
        "page",
        "unit_page",
        "reason",
        "authority",
        "reviewer",
        "timezone",
        "duplicate_unit",
        "snapshot",
        "reference_hash",
        "missing_reference",
        "bool_page",
    ],
)
def test_documentary_bundle_rejects_nonofficial_stale_or_promoted_data(
    documentary_data, defect
):
    data = deepcopy(documentary_data)
    bundle = data["documentary_bundle"]
    source, unit = bundle["sources"][0], bundle["units"][0]
    if defect in {"nonofficial", "spoofed_host", "http"}:
        source["source_url"] = {
            "nonofficial": "https://notebooklm.google.com/resumen.pdf",
            "spoofed_host": "https://www3.congreso.gob.pe.evil.invalid/f.pdf",
            "http": "http://www3.congreso.gob.pe/f.pdf",
        }[defect]
    elif defect == "id":
        source["id"] = "pdf-sha256-" + "a" * 64
    elif defect in {"pdf_hash", "md_hash", "layout_hash"}:
        field = {
            "pdf_hash": "pdf",
            "md_hash": "markdown",
            "layout_hash": "docling_json",
        }[defect]
        source[field]["sha256"] = "a" * 64
    elif defect == "not_pdf":
        path = source["pdf"]["path"]
        from pathlib import Path

        Path(path).write_bytes(b"This is not a PDF")
        source["pdf"]["sha256"] = sha256(b"This is not a PDF").hexdigest()
        source["id"] = "pdf-sha256-" + source["pdf"]["sha256"]
        unit["source_id"] = source["id"]
    elif defect == "rewritten_md":
        from pathlib import Path

        Path(source["markdown"]["path"]).write_bytes(
            b"Resumen generado, no exportacion"
        )
        source["markdown"]["sha256"] = sha256(
            b"Resumen generado, no exportacion"
        ).hexdigest()
    elif defect == "span_hash":
        unit["text_sha256"] = "a" * 64
    elif defect == "span_end":
        unit["end"] = 999999
    elif defect == "page":
        source["selected_pdf_pages"] = [2]
    elif defect == "unit_page":
        unit["pdf_pages"] = [2]
    elif defect == "bool_page":
        unit["pdf_pages"] = [True]
    elif defect == "reason":
        unit["reason"] = " "
    elif defect == "authority":
        unit["valid_from"] = "2020-01-01"
    elif defect == "reviewer":
        bundle["reviewer"] = " "
    elif defect == "timezone":
        bundle["reviewed_at"] = "2026-10-11T12:00:00"
    elif defect == "duplicate_unit":
        bundle["units"].append(deepcopy(unit))
    elif defect == "snapshot":
        data["snapshot"]["nodes"][0]["provenance_state"] = "reviewed"
    elif defect == "reference_hash":
        data["cases"][0]["reference_spans"][0]["text_sha256"] = "a" * 64
    else:
        data["cases"][0]["reference_spans"] = []
    with pytest.raises(ValueError):
        validate_dataset(data)


def test_documentary_search_preserves_offsets_and_requires_explicit_edition(
    documentary_data,
):
    data = documentary_data
    engine = DocumentaryRetriever(data["snapshot"])
    plan = DocumentaryPlan(**data["cases"][0]["plan"], top_k=1)
    result = engine.search(plan)
    assert result["engine"] == "official_pdf_documentary_research"
    assert "as_of" not in result
    hit = result["hits"][0]
    assert hit["provenance_state"] == "ai_documentary"
    assert not {"valid_from", "valid_to", "checked_through"} & hit.keys()
    from pathlib import Path

    md = Path(data["documentary_bundle"]["sources"][0]["markdown"]["path"]).read_text(
        encoding="utf-8"
    )
    assert md[hit["start"] : hit["end"]] == hit["content"]
    assert (
        engine.search(plan.model_copy(update={"source_ids": ["absent-edition"]}))[
            "state"
        ]
        == "abstain"
    )
    with pytest.raises(ValueError):
        DocumentaryPlan(
            query="alimentos", source_ids=plan.source_ids, as_of="2026-10-11"
        )
    with pytest.raises(ValueError):
        engine.search(SearchPlan(query="alimentos", as_of="2026-10-11"))


def test_documentary_benchmark_is_labeled_and_pairs_all_rankers(documentary_data):
    result = run(documentary_data, repetitions=2)
    assert result["dataset_kind"] == "official_pdf_documentary"
    assert len(result["records"]) == 6
    assert all(r["scores"]["recall"] == 1 for r in result["records"])
    assert all(r["reference_span_recall"] == 1 for r in result["records"])
    assert all(r["api"]["requests"] == 0 for r in result["records"])
    assert "gold documental IA" in result["limitations"][0]


@pytest.mark.parametrize(
    "defect",
    [None, "rewrite_text", "real_marker", "hash", "duplicate", "missing_raw", "reason"],
)
def test_docling_paragraph_correction_is_metadata_only_and_traceable(
    documentary_data, tmp_path, defect
):
    bundle = deepcopy(documentary_data["documentary_bundle"])
    source = bundle["sources"][0]
    document = DoclingDocument(name="list-fixture")
    group = document.add_group(label=GroupLabel.LIST, name="list")
    item = document.add_list_item(
        text="Continuación ficticia sin numeral.",
        enumerated=False,
        marker="",
        parent=group,
    )
    raw = document.export_to_dict(mode="json")
    corrected = deepcopy(raw)
    corrected["texts"][0]["label"] = "text"
    corrected["texts"][0].pop("marker")
    corrected["texts"][0].pop("enumerated")
    correction = {
        "text_ref": item.self_ref,
        "text_sha256": sha256(item.text.encode()).hexdigest(),
        "reason": "Fixture: reclasificar sin cambiar texto.",
    }
    if defect == "rewrite_text":
        corrected["texts"][0]["text"] = "Contenido inventado"
    elif defect == "real_marker":
        raw["texts"][0]["marker"] = "1."
    elif defect == "hash":
        correction["text_sha256"] = "a" * 64
    elif defect == "reason":
        correction["reason"] = " "
    markdown = DoclingDocument.model_validate(corrected).export_to_markdown()
    paths = {
        "raw_docling_json": tmp_path / "raw.json",
        "docling_json": tmp_path / "corrected.json",
        "markdown": tmp_path / "corrected.md",
    }
    paths["raw_docling_json"].write_text(json.dumps(raw), encoding="utf-8")
    paths["docling_json"].write_text(json.dumps(corrected), encoding="utf-8")
    paths["markdown"].write_bytes(markdown.encode())
    for field, path in paths.items():
        source[field] = {
            "path": str(path),
            "sha256": sha256(path.read_bytes()).hexdigest(),
        }
    source["paragraph_corrections"] = [correction] * (2 if defect == "duplicate" else 1)
    if defect == "missing_raw":
        source.pop("raw_docling_json")
    bundle["units"][0].update(
        start=0, end=len(markdown), text_sha256=sha256(markdown.encode()).hexdigest()
    )
    original_bytes = paths["raw_docling_json"].read_bytes()
    if defect:
        with pytest.raises(ValueError):
            build_snapshot(bundle)
    else:
        snapshot = build_snapshot(bundle)
        assert (
            next(n["text"] for n in snapshot["nodes"] if n["type"] == "DocumentaryText")
            == markdown
        )
    assert paths["raw_docling_json"].read_bytes() == original_bytes


@pytest.mark.parametrize(
    "text",
    [
        "",
        " \t\r\n",
        "Árbol 👩🏽‍⚖️ e\u0301\r\n" * 100,
        "A" * 3100,
        "Primer párrafo.\r\n\r\nSegundo párrafo.\n" * 100,
    ],
)
@pytest.mark.parametrize("policy", ["fixed", "paragraph"])
def test_documentary_windows_preserve_exact_bounded_unicode_partition(text, policy):
    windows = list(documentary_windows(text, 100, policy))
    assert "".join(text[start:end] for start, end in windows) == text
    assert all(0 < end - start <= 100 for start, end in windows)
    assert all(left[1] == right[0] for left, right in zip(windows, windows[1:]))


def test_paragraph_policy_prevents_known_reference_boundary_loss(documentary_data):
    text = "A" * 900 + "\n\n" + "B" * 90 + " referencia completa " + "C" * 100
    start = text.index("referencia completa")
    end = start + len("referencia completa")
    assert not any(
        a <= start < end <= b for a, b in documentary_windows(text, 1000, "fixed")
    )
    assert any(
        a <= start < end <= b for a, b in documentary_windows(text, 1000, "paragraph")
    )
    data = documentary_data
    plan = DocumentaryPlan(**data["cases"][0]["plan"], chunk_policy="paragraph")
    result = DocumentaryRetriever(data["snapshot"]).search(plan)
    assert all(hit["chunk_policy"] == "paragraph" for hit in result["hits"])
    assert all(hit["provenance_state"] == "ai_documentary" for hit in result["hits"])


@pytest.mark.parametrize("limit,policy", [(0, "fixed"), (100, "unknown")])
def test_documentary_windows_reject_invalid_policy(limit, policy):
    with pytest.raises(ValueError):
        list(documentary_windows("texto", limit, policy))


def child_bundle(data):
    bundle = deepcopy(data["documentary_bundle"])
    parent = bundle["units"][0]
    start, end = 16, 25  # "alimentos", dentro del texto ficticio.
    child = {
        **parent,
        "component": "article/1/inciso/a",
        "parent_component": "article/1",
        "kind": "inciso",
        "label": "Inciso ficticio",
        "start": start,
        "end": end,
        "text_sha256": sha256(b"alimentos").hexdigest(),
    }
    bundle["units"].append(child)
    return bundle


def test_documentary_memberships_bind_exact_nested_spans_and_preserve_v1_defaults(
    documentary_data,
):
    from research.documentary import documentary_root_map

    original = deepcopy(documentary_data["documentary_bundle"])
    explicit = deepcopy(original)
    explicit["units"][0].update(kind="article", parent_component=None)
    assert (
        build_snapshot(original)
        == build_snapshot(explicit)
        == documentary_data["snapshot"]
    )
    bundle = child_bundle(documentary_data)
    child = bundle["units"][1]
    bundle["units"].append(
        {
            **child,
            "kind": "numeral",
            "parent_component": child["component"],
            "component": child["component"] + "/numeral/1",
            "label": "Numeral ficticio anidado",
            "start": 17,
            "end": 20,
            "text_sha256": sha256(b"lim").hexdigest(),
        }
    )
    snapshot = build_snapshot(bundle)
    edge = next(e for e in snapshot["edges"] if e["type"] == "contains_version")
    roots = documentary_root_map(snapshot)
    assert roots[edge["target"]] == roots[edge["source"]] == edge["source"]
    assert all(
        n.get("provenance_state") != "reviewed" and n["type"] != "CTV"
        for n in snapshot["nodes"]
    )
    engine = DocumentaryRetriever(snapshot)
    plan = DocumentaryPlan(**documentary_data["cases"][0]["plan"], strategy="ppr")
    chunks = engine.chunks(plan)
    seed = next(c["id"] for c in chunks if c["version_id"] == edge["target"])
    assert len(engine._ppr(chunks, [seed])) == 3
    assert list(engine._ppr(chunks, [seed], use_memberships=False)) == [seed]
    assert engine.search(plan)["ppr_status"]["eligible_membership_edges"] == 2
    disabled = plan.model_copy(update={"membership_policy": "disabled"})
    assert engine.search(disabled)["ppr_status"]["expanded_versions"] == 0
    assert engine.search(disabled)["ppr_status"]["used_membership_edges"] == 0
    constrained = plan.model_copy(
        update={
            "resource_ids": [bundle["units"][0]["resource_id"]],
            "component": "article/1",
        }
    )
    assert engine.search(constrained)["ppr_status"]["eligible_membership_edges"] == 0
    assert len(engine.chunks(constrained)) == 1


@pytest.mark.parametrize(
    "defect",
    [
        "missing_parent",
        "other_resource",
        "other_source",
        "outside",
        "identical",
        "sibling_overlap",
        "child_without_parent",
        "article_with_parent",
        "wrong_path",
        "bad_kind",
    ],
)
def test_documentary_memberships_reject_unverifiable_structure(
    documentary_data, defect
):
    bundle = child_bundle(documentary_data)
    parent, child = bundle["units"]
    if defect == "missing_parent":
        child.update(parent_component="article/2", component="article/2/inciso/a")
    elif defect == "other_resource":
        child.update(resource_id="pe:other", resource_title="Otro recurso ficticio")
    elif defect == "other_source":
        child["source_id"] = "pdf-sha256-" + "a" * 64
    elif defect in {"outside", "identical"}:
        if defect == "outside":
            parent.update(
                end=20, text_sha256=sha256(b"Regla ficticia: alim").hexdigest()
            )
        else:
            child.update(
                start=parent["start"],
                end=parent["end"],
                text_sha256=parent["text_sha256"],
            )
    elif defect == "sibling_overlap":
        bundle["units"].append({**child, "component": "article/1/inciso/b"})
    elif defect == "child_without_parent":
        child["parent_component"] = None
    elif defect == "article_with_parent":
        child["kind"] = "article"
    elif defect == "wrong_path":
        child["component"] = "article/99/inciso/a"
    else:
        child["kind"] = "invented_authority"
    with pytest.raises(ValueError):
        build_snapshot(bundle)


def test_documentary_root_metrics_deduplicate_children_but_require_actual_span(
    documentary_data,
):
    from research.documentary import documentary_root_map
    from research.sat_benchmark import score_reference_spans

    data = deepcopy(documentary_data)
    data["documentary_bundle"] = child_bundle(data)
    data["snapshot"] = build_snapshot(data["documentary_bundle"])
    data["evaluation_level"] = "documentary_root"
    roots = documentary_root_map(data["snapshot"])
    child = next(v for v, root in roots.items() if v != root)
    root = roots[child]
    ref = data["cases"][0]["reference_spans"][0]
    ref.update(version_id=root)
    assert (
        score_reference_spans(
            [ref], [{"version_id": child, "start": 16, "end": 25}], root_map=roots
        )
        == 0
    )
    ref.update(start=16, end=25, text_sha256=sha256(b"alimentos").hexdigest())
    data["cases"][0]["expected_version_ids"] = [root]
    data["config"].update(top_k=3)
    result = run(data, repetitions=2)
    assert result["evaluation_level"] == "documentary_root"
    assert all(
        r["scores"]["matched"] == r["scores"]["retrieved"] == 1
        for r in result["records"]
    )
    assert all(r["reference_span_recall"] == 1 for r in result["records"])
    assert any(
        len(set(r["runs"][0])) == 2 and len(set(r["evaluation_runs"][0])) == 1
        for r in result["records"]
    )
    data["cases"][0]["expected_version_ids"] = [child]
    with pytest.raises(ValueError, match="raíz"):
        validate_dataset(data)


@pytest.mark.parametrize("defect", ["cycle", "multiple_parents", "cross_edition"])
def test_documentary_root_mapping_rejects_ambiguous_or_cyclic_graph(
    documentary_data, defect
):
    from research.documentary import documentary_root_map

    snapshot = build_snapshot(child_bundle(documentary_data))
    edge = next(e for e in snapshot["edges"] if e["type"] == "contains_version")
    if defect == "cycle":
        snapshot["edges"].append(
            {
                "type": "contains_version",
                "source": edge["target"],
                "target": edge["source"],
            }
        )
    elif defect == "multiple_parents":
        snapshot["edges"].append(deepcopy(edge))
    else:
        next(n for n in snapshot["nodes"] if n["id"] == edge["target"])[
            "evidence_id"
        ] = "different-edition"
    with pytest.raises(ValueError):
        documentary_root_map(snapshot)
