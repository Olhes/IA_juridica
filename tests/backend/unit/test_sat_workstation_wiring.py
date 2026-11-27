"""HTTP wiring and asset allowlist tests for SAT review workstation & main app."""
from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from config.settings import settings
from ingestion.sat_graph.store import digest
from sat_review_app import create_local_app
from services.sat_corpus import CorpusEditor
from services.sat_corpus_routes import ALLOWED_ASSETS
from services.sat_provenance_routes import workspace_service
from tests.backend.fixtures.sat_store import FixtureSATStore as SATGraphStore

EXPECTED_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; "
    "frame-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'self'"
)


@pytest.fixture
def fixture_corpus(tmp_path):
    store = SATGraphStore(tmp_path / "wiring.sqlite3")
    markdown = (
        "Ley N° 28970\n"
        "Artículo 1. Objeto\n"
        "El Poder Judicial deberá administrar el REDAM conforme a la Ley N° 27444.\n"
    )
    a1 = markdown.index("Artículo 1.")
    spans = [
        ("root", "instrument", 0, len(markdown), None),
        ("art1", "article", a1, len(markdown), "root"),
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
                {"revision_id": "revision", "source_node_id": identity, "label": identity, "kind": kind, **audit},
            )
            store._node(
                db,
                "w:" + identity,
                "Work",
                {"resource_id": "pe:ley:28970", "component": identity, "label": identity, "kind": kind},
            )
            store._node(
                db,
                "v:" + identity,
                "CTV",
                {
                    "work_id": "w:" + identity,
                    "scope": "PE",
                    "valid_from": None,
                    "valid_to": None,
                    "checked_through": "2026-11-12",
                    "snapshot_as_of": "2026-11-12",
                    "provenance_state": "user_attested_snapshot",
                    "documentary_revision": "revision",
                    **audit,
                },
            )
            store._node(db, "t:" + identity, "CLV", {"language": "es", "text": markdown[start:end], **audit})
            store._edge(db, "v:" + identity, "has_text", "t:" + identity, {})
            store._edge(db, "v:" + identity, "derived_from_documentary", identity, {})
            if parent:
                store._edge(db, parent, "documentary_has_part", identity, {})
                store._edge(db, "w:" + parent, "has_part", "w:" + identity, {})
                store._edge(db, "v:" + parent, "contains_version", "v:" + identity, {})
    return CorpusEditor(store)


def test_local_app_serves_csp_allowlisted_assets_and_mounted_routers(fixture_corpus, monkeypatch):
    workspace_service.clear_cache()
    monkeypatch.setattr("services.sat_corpus_routes.runtime_sat_store", lambda: fixture_corpus.store)
    monkeypatch.setattr(settings, "COHERE_API_KEY", "")

    app = create_local_app("test-cap")
    client = TestClient(app)

    # Unauthenticated calls to protected provenance & temporal APIs must fail with 403.
    assert client.get("/sat-graph/review/provenance/capabilities").status_code == 403
    assert client.get("/sat-graph/review/temporal/samples").status_code == 403

    # Strict CSP header on /sat-graph/review shell.
    page = client.get("/sat-graph/review")
    assert page.status_code == 200
    assert page.headers["content-security-policy"] == EXPECTED_CSP
    assert 'data-tab="provenance"' in page.text
    assert 'data-tab="temporal"' in page.text

    # All 7 allowlisted assets serve with 200; unknown/traversal paths return 404.
    expected_assets = {
        "editor.js",
        "editor.css",
        "favicon.svg",
        "workstation-panels.css",
        "temporal-engine.js",
        "temporal-viewer.js",
        "graphragprov.js",
    }
    assert ALLOWED_ASSETS == expected_assets
    for asset_name in expected_assets:
        res = client.get(f"/sat-graph/review/assets/{asset_name}")
        assert res.status_code == 200, f"Asset {asset_name} failed with {res.status_code}"
        assert len(res.content) > 0

    for bad_name in ("unknown.js", "..%2Findex.html", "index.html", "sat_graph.surql.gz"):
        res = client.get(f"/sat-graph/review/assets/{bad_name}")
        assert res.status_code == 404

    # Bootstrap local session cookie.
    boot = client.get("/local-session/test-cap", follow_redirects=False)
    assert boot.status_code == 303

    # Provenance routes mounted on local app.
    caps = client.get("/sat-graph/review/provenance/capabilities")
    assert caps.status_code == 200
    assert caps.json()["offline_ready"] is True

    parsed = client.post(
        "/sat-graph/review/provenance/polynomial/parse",
        headers={"X-SAT-Review": "1"},
        json={"expression": "(+ (* occ_000000000001 occ_000000000002) occ_000000000003)"},
    )
    assert parsed.status_code == 200
    assert parsed.json()["total_multiplicity"] == 2

    graph = client.post(
        "/sat-graph/review/documents/pe:ley:28970/provenance-graph",
        headers={"X-SAT-Review": "1"},
        json={"mode": "deterministic"},
    )
    assert graph.status_code == 200
    assert graph.json()["doc_id"] == "pe:ley:28970"

    # Temporal routes mounted on local app.
    samples = client.get("/sat-graph/review/temporal/samples")
    assert samples.status_code == 200
    sample_ids = {s["id"] for s in samples.json()["samples"]}
    assert sample_ids == {"pe-amendment-chain", "pe-interpretive-overlay"}

    dataset = client.get("/sat-graph/review/temporal/dataset/pe:ley:28970")
    assert dataset.status_code == 200
    assert dataset.json()["resourceId"] == "pe:ley:28970"


def _collect_route_paths(routes) -> set[str]:
    paths: set[str] = set()
    for route in routes:
        path = getattr(route, "path", None)
        if isinstance(path, str):
            paths.add(path)
        nested = getattr(route, "routes", None)
        if nested:
            paths.update(_collect_route_paths(nested))
    return paths


def test_main_app_mounts_provenance_and_temporal_routers_when_sat_enabled():
    import main as backend_main

    if settings.RAG_ENGINE.lower() == "sat":
        openapi_paths = set(backend_main.app.openapi().get("paths", {}).keys())
        route_paths = _collect_route_paths(backend_main.app.routes) | openapi_paths
        assert "/sat-graph/review/provenance/capabilities" in route_paths
        assert "/sat-graph/review/documents/{resource_id}/provenance-graph" in route_paths
        assert "/sat-graph/review/documents/{resource_id}/provenance-query" in route_paths
        assert "/sat-graph/review/temporal/dataset" in route_paths
        assert "/sat-graph/review/temporal/dataset/{resource_id}" in route_paths
        assert "/sat-graph/review/temporal/samples" in route_paths

        # Live TestClient dispatch (no lifespan) confirms routes resolve and enforce auth (not 404).
        client = TestClient(backend_main.app)
        try:
            assert client.get("/sat-graph/review/provenance/capabilities").status_code in (401, 403)
            assert client.get("/sat-graph/review/temporal/samples").status_code in (401, 403)
        finally:
            client.close()
    else:
        assert hasattr(backend_main, "sat_provenance_router")
        assert hasattr(backend_main, "sat_temporal_router")
