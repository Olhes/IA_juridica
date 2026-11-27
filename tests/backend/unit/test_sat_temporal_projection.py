"""Unit and HTTP tests for SAT-Graph Viewer temporal projection and routes."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from ingestion.sat_graph.contracts import ReviewManifest, ReviewedAction, ReviewedUnit
from ingestion.sat_graph.store import digest, version_id, work_id
from ingestion.source_evidence import SourceEvidence
from services.sat_corpus import CorpusEditor, Edition, Publication, TextEdit, replace_text
from services.sat_temporal_projection import (
    UnknownResourceError,
    ViewerDataset,
    bundled_viewer_samples,
    normalize_instant_iso,
    project_sat_graph_to_viewer_dataset,
)
from services.sat_temporal_routes import router as temporal_router
from tests.backend.fixtures.sat_store import FixtureSATStore


@pytest.fixture
def snapshot_corpus(tmp_path):
    store = FixtureSATStore(tmp_path / "sat-snapshot.sqlite3")
    markdown = (
        "Ley de prueba\n"
        "Artículo 1. Alimentos\n"
        "a) Protección a la niñez.\n"
        "Artículo 2. Registro.\n"
    )
    spans = [
        ("root", "instrument", 0, len(markdown), None),
        ("art1", "article", markdown.index("Artículo 1"), markdown.index("Artículo 2"), "root"),
        ("inciso", "inciso", markdown.index("a)"), markdown.index("Artículo 2"), "art1"),
        ("art2", "article", markdown.index("Artículo 2"), len(markdown), "root"),
    ]
    with store._transaction() as db:
        store._node(db, "source", "Source", {})
        db.execute("INSERT INTO sat_documents VALUES (?,?,'reviewed')", ("source", markdown))
        store._node(
            db,
            "revision",
            "DocumentaryRevision",
            {
                "directory": "ley-28970",
                "evidence_id": "source",
                "markdown": markdown,
                "markdown_sha256": digest(markdown),
                "review_hash": "original",
            },
        )
        for identity, kind, start, end, parent in spans:
            audit = {
                "start": start,
                "end": end,
                "text_sha256": digest(markdown[start:end]),
                "evidence_id": "source",
                "review_id": "original",
                "source_url": "https://example.org",
            }
            store._node(
                db,
                identity,
                "DocumentaryComponent",
                {
                    "revision_id": "revision",
                    "source_node_id": identity,
                    "label": identity,
                    "kind": kind,
                    **audit,
                },
            )
            store._node(
                db,
                "w:" + identity,
                "Work",
                {
                    "resource_id": "pe:ley:28970",
                    "component": identity,
                    "label": identity,
                    "kind": kind,
                },
            )
            ctv_payload = {
                "work_id": "w:" + identity,
                "scope": "PE",
                "valid_from": None,
                "valid_to": None,
                "checked_through": "2026-11-12",
                "snapshot_as_of": "2026-11-12",
                "provenance_state": "user_attested_snapshot",
                "documentary_revision": "revision",
                **audit,
            }
            if identity == "art2":
                ctv_payload["amending_source"] = {
                    "id": "pe:dl:1377",
                    "title": "Decreto Legislativo N.° 1377",
                    "url": "https://spij.minjus.gob.pe/",
                }
            store._node(db, "v:" + identity, "CTV", ctv_payload)
            store._node(
                db,
                "t:" + identity,
                "CLV",
                {"language": "es", "text": markdown[start:end], **audit},
            )
            store._edge(db, "v:" + identity, "has_text", "t:" + identity, {})
            store._edge(db, "v:" + identity, "derived_from_documentary", identity, {})
            if parent:
                store._edge(db, parent, "documentary_has_part", identity, {})
                store._edge(db, "w:" + parent, "has_part", "w:" + identity, {})
                store._edge(db, "v:" + parent, "contains_version", "v:" + identity, {})
    return CorpusEditor(store)


@pytest.fixture
def normative_action_store(tmp_path):
    store = FixtureSATStore(tmp_path / "sat-actions.sqlite3")
    md_v1 = "Artículo 1. Texto original del artículo de prueba."
    ev1 = SourceEvidence(
        schema_version=1,
        evidence_id="pdf-sha256-" + ("a" * 64),
        pdf_sha256="a" * 64,
        markdown_sha256=digest(md_v1),
        pdf_size_bytes=128,
        markdown_size_bytes=len(md_v1.encode("utf-8")),
        provenance_state="unverified",
    )
    store.stage(ev1, md_v1)

    unit_v1 = ReviewedUnit(
        resource_id="pe:ley:28970",
        component="art-1",
        label="Artículo 1",
        valid_from=date(2007, 1, 27),
        start=0,
        end=len(md_v1),
        text_sha256=digest(md_v1),
    )
    v1_id = version_id(unit_v1)
    manifest_v1 = ReviewManifest(
        evidence_id=ev1.evidence_id,
        pdf_sha256=ev1.pdf_sha256,
        markdown_sha256=ev1.markdown_sha256,
        source_resource_id="pe:ley:28970",
        checked_through=date(2020, 12, 31),
        reviewer="legal-reviewer",
        reviewed_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
        effective_date_basis="Diario Oficial El Peruano",
        units=[unit_v1],
        actions=[
            ReviewedAction(
                action_key="enact-28970",
                kind="enact",
                effective_on=date(2007, 1, 27),
                produces=[v1_id],
                start=0,
                end=len(md_v1),
                text_sha256=digest(md_v1),
            )
        ],
    )
    store.review(manifest_v1)

    md_v2 = "Artículo 1. Texto reformado con conciliación extrajudicial."
    ev2 = SourceEvidence(
        schema_version=1,
        evidence_id="pdf-sha256-" + ("b" * 64),
        pdf_sha256="b" * 64,
        markdown_sha256=digest(md_v2),
        pdf_size_bytes=256,
        markdown_size_bytes=len(md_v2.encode("utf-8")),
        provenance_state="unverified",
    )
    store.stage(ev2, md_v2)

    unit_v2 = ReviewedUnit(
        resource_id="pe:ley:28970",
        component="art-1",
        label="Artículo 1",
        valid_from=date(2018, 9, 12),
        start=0,
        end=len(md_v2),
        text_sha256=digest(md_v2),
    )
    v2_id = version_id(unit_v2)
    manifest_v2 = ReviewManifest(
        evidence_id=ev2.evidence_id,
        pdf_sha256=ev2.pdf_sha256,
        markdown_sha256=ev2.markdown_sha256,
        source_resource_id="pe:ley:28970",
        checked_through=date(2025, 1, 3),
        reviewer="legal-reviewer",
        reviewed_at=datetime(2025, 1, 4, tzinfo=timezone.utc),
        effective_date_basis="Diario Oficial El Peruano",
        units=[unit_v2],
        actions=[
            ReviewedAction(
                action_key="amend-28970-2018",
                kind="amend",
                effective_on=date(2018, 9, 12),
                terminates=[v1_id],
                produces=[v2_id],
                start=0,
                end=len(md_v2),
                text_sha256=digest(md_v2),
            )
        ],
    )
    store.review(manifest_v2)

    # Add an interpretive overlay CTV on the same Work to verify interpretive projection.
    wid = work_id("pe:ley:28970", "art-1")
    with store._transaction() as db:
        store._node(
            db,
            "ctv:interp:1",
            "CTV",
            {
                "work_id": wid,
                "scope": "PE",
                "valid_from": "2020-05-01",
                "valid_to": None,
                "version_type": "interpretive",
                "provenance_state": "interpretive",
            },
        )
        store._node(
            db,
            "clv:interp:1",
            "CLV",
            {
                "language": "es",
                "aspect": "holding",
                "text": "Criterio jurisdiccional sobre interpretación del Artículo 1.",
            },
        )
        store._edge(db, "ctv:interp:1", "version_of", wid, {})
        store._edge(db, "ctv:interp:1", "has_text", "clv:interp:1", {})

    return store, v1_id, v2_id


def test_normalize_instant_iso_enforces_utc_and_rejects_naive():
    assert normalize_instant_iso("2026-11-12") == "2026-11-12T00:00:00Z"
    assert normalize_instant_iso("2026-11-12T05:00:00-05:00") == "2026-11-12T10:00:00Z"
    assert normalize_instant_iso("2026-11-12T10:00:00+00:00") == "2026-11-12T10:00:00Z"
    assert normalize_instant_iso(None) is None
    with pytest.raises(ValueError):
        normalize_instant_iso("2026-11-12T10:00:00")


def test_projection_preserves_null_validity_and_separates_editorial_revisions(snapshot_corpus):
    edition = Edition.model_validate(snapshot_corpus.get("pe:ley:28970")["edition"])
    edited = replace_text(
        TextEdit(
            edition=edition,
            component_id="inciso",
            text="a) Protección integral a la niñez.\n",
        )
    )
    snapshot_corpus.apply(
        "pe:ley:28970",
        Publication(edition=edited, reason="Cotejo editorial contra PDF oficial"),
        "human-reviewer",
    )

    graph = snapshot_corpus.store.export()
    dataset = project_sat_graph_to_viewer_dataset(
        graph,
        resource_id="pe:ley:28970",
        include_editorial_history=True,
    )

    assert dataset.schemaVersion == "sat-graph-viewer/1"
    assert dataset.source == "live-corpus"
    assert dataset.resourceId == "pe:ley:28970"

    item_by_id = {item.id: item for item in dataset.items}
    assert "pe:ley:28970" in item_by_id
    assert item_by_id["w:root"].parentId == "pe:ley:28970"
    assert item_by_id["w:art1"].parentId == "w:root"
    assert item_by_id["w:inciso"].parentId == "w:art1"

    # Both archived (4) and active (4) CTVs must be projected.
    assert len(dataset.versions) == 8
    archived_versions = [v for v in dataset.versions if v.metadata["archived"]]
    active_versions = [v for v in dataset.versions if not v.metadata["archived"]]
    assert len(archived_versions) == 4
    assert len(active_versions) == 4

    # CRITICAL INVARIANT: never synthesize legal validity dates when valid_from is None.
    for v in dataset.versions:
        assert v.validityInterval == (None, None)
        assert v.metadata["legalIntervalKnown"] is False
        assert v.metadata["snapshotAsOf"] == "2026-11-12T00:00:00Z"
        assert "provenance" in v.metadata
        assert "editorialSupersededBy" in v.metadata
        assert "documentaryRevision" in v.metadata
        assert "retrievable" in v.metadata

    assert all(v.metadata["editorialSupersededBy"] is not None for v in archived_versions)
    assert all(v.metadata["editorialSupersededBy"] is None for v in active_versions)
    assert len(dataset.textUnits) == 8
    assert all(tu.sourceType == "Version" and tu.aspect == "canonical" for tu in dataset.textUnits)

    # Editorial revision action must link superseded CTVs -> new CTVs, marked syntheticKind='editorial'.
    editorial_actions = [a for a in dataset.actions if a.kind == "editorial_revision"]
    assert len(editorial_actions) == 1
    ed_action = editorial_actions[0]
    assert ed_action.metadata["syntheticKind"] == "editorial"
    assert ed_action.eventTime is not None and ed_action.eventTime.endswith("Z")
    assert set(ed_action.terminatesVersionIds) == {v.id for v in archived_versions}
    assert set(ed_action.producesVersionIds) == {v.id for v in active_versions}

    # amending_source reference must be projected cleanly with eventTime=None (never fabricating dates).
    amend_refs = [a for a in dataset.actions if a.kind == "amend_reference"]
    assert len(amend_refs) >= 1
    assert all(a.eventTime is None for a in amend_refs)
    assert all(a.sourceId == "pe:dl:1377" for a in amend_refs)
    assert all(a.metadata["legalDateKnown"] is False for a in amend_refs)

    # Opting out of editorial history removes editorial_revision actions cleanly.
    without_editorial = project_sat_graph_to_viewer_dataset(
        graph,
        resource_id="pe:ley:28970",
        include_editorial_history=False,
    )
    assert [a for a in without_editorial.actions if a.kind == "editorial_revision"] == []


def test_projection_handles_normative_actions_interpretive_versions_and_full_corpus(normative_action_store):
    store, v1_id, v2_id = normative_action_store
    graph = store.export()

    dataset = project_sat_graph_to_viewer_dataset(graph, resource_id="pe:ley:28970")
    by_id = {v.id: v for v in dataset.versions}
    assert by_id[v1_id].type == "statutory"
    assert by_id[v1_id].validityInterval == ("2007-01-27T00:00:00Z", "2018-09-12T00:00:00Z")
    assert by_id[v1_id].metadata["legalIntervalKnown"] is True

    assert by_id[v2_id].type == "statutory"
    assert by_id[v2_id].validityInterval == ("2018-09-12T00:00:00Z", None)
    assert by_id[v2_id].metadata["legalIntervalKnown"] is True

    assert by_id["ctv:interp:1"].type == "interpretive"
    assert by_id["ctv:interp:1"].validityInterval == ("2020-05-01T00:00:00Z", None)

    normative_actions = [a for a in dataset.actions if a.metadata.get("syntheticKind") == "normative"]
    assert [a.kind for a in normative_actions] == ["enact", "amend"]
    enact, amend = normative_actions
    assert enact.eventTime == "2007-01-27T00:00:00Z"
    assert enact.producesVersionIds == [v1_id]
    assert amend.eventTime == "2018-09-12T00:00:00Z"
    assert amend.terminatesVersionIds == [v1_id]
    assert amend.producesVersionIds == [v2_id]

    full_corpus = project_sat_graph_to_viewer_dataset(graph, resource_id=None)
    assert full_corpus.resourceId is None
    assert {v.id for v in full_corpus.versions} == {v1_id, v2_id, "ctv:interp:1"}

    with pytest.raises(UnknownResourceError):
        project_sat_graph_to_viewer_dataset(graph, resource_id="pe:ley:inexistente")


def test_bundled_viewer_samples_are_schema_valid_and_rich():
    samples = bundled_viewer_samples()
    assert len(samples) == 2
    by_id = {s["id"]: s for s in samples}
    assert set(by_id.keys()) == {"pe-amendment-chain", "pe-interpretive-overlay"}

    for sample in samples:
        parsed = ViewerDataset.model_validate(sample["dataset"])
        assert parsed.schemaVersion == "sat-graph-viewer/1"
        assert len(parsed.items) >= 2
        assert len(parsed.versions) == 3
        assert len(parsed.actions) == 3
        assert len(parsed.textUnits) == 3

    chain = ViewerDataset.model_validate(by_id["pe-amendment-chain"]["dataset"])
    assert all(v.type == "statutory" for v in chain.versions)
    assert chain.versions[0].validityInterval[1] == chain.versions[1].validityInterval[0]
    assert chain.versions[1].validityInterval[1] == chain.versions[2].validityInterval[0]
    assert chain.versions[2].validityInterval[1] is None

    overlay = ViewerDataset.model_validate(by_id["pe-interpretive-overlay"]["dataset"])
    assert [v.type for v in overlay.versions] == ["statutory", "interpretive", "interpretive"]
    assert overlay.versions[0].validityInterval[1] is None
    assert all(a.terminatesVersionIds == [] for a in overlay.actions if a.kind == "interpret")


@pytest.fixture
def temporal_client(snapshot_corpus, monkeypatch):
    from sat_review_app import create_local_app

    monkeypatch.setattr("services.sat_corpus_routes.runtime_sat_store", lambda: snapshot_corpus.store)
    app = create_local_app("test-temporal-token")
    app.include_router(temporal_router)
    with TestClient(app) as client:
        yield client


def test_temporal_routes_enforce_auth_and_serve_datasets_and_samples(temporal_client):
    assert temporal_client.get("/sat-graph/review/temporal/dataset/pe:ley:28970").status_code == 403
    assert temporal_client.get("/sat-graph/review/temporal/dataset").status_code == 403
    assert temporal_client.get("/sat-graph/review/temporal/samples").status_code == 403

    auth = temporal_client.get("/local-session/test-temporal-token", follow_redirects=False)
    assert auth.status_code == 303

    doc_res = temporal_client.get("/sat-graph/review/temporal/dataset/pe:ley:28970")
    assert doc_res.status_code == 200
    doc_payload = ViewerDataset.model_validate(doc_res.json())
    assert doc_payload.resourceId == "pe:ley:28970"
    assert len(doc_payload.versions) == 4
    assert all(v.validityInterval == (None, None) for v in doc_payload.versions)
    assert all(v.metadata["legalIntervalKnown"] is False for v in doc_payload.versions)

    corpus_res = temporal_client.get("/sat-graph/review/temporal/dataset?include_editorial_history=false")
    assert corpus_res.status_code == 200
    corpus_payload = ViewerDataset.model_validate(corpus_res.json())
    assert corpus_payload.resourceId is None
    assert corpus_payload.metadata["includeEditorialHistory"] is False

    missing_res = temporal_client.get("/sat-graph/review/temporal/dataset/pe:ley:does-not-exist")
    assert missing_res.status_code == 404

    samples_res = temporal_client.get("/sat-graph/review/temporal/samples")
    assert samples_res.status_code == 200
    samples_body = samples_res.json()
    assert "samples" in samples_body and len(samples_body["samples"]) == 2
