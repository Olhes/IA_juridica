"""HTTP contract tests for GraphRAGProv routes mounted alongside SAT corpus review."""
from __future__ import annotations

import secrets

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient
import pytest

from config.settings import settings
from ingestion.sat_graph.store import digest
from services.quality_access import require_quality_admin
from services.sat_corpus import CorpusEditor, Edition, TextEdit, replace_text
from services.sat_corpus_routes import router as review_router
from services.sat_provenance_routes import router as provenance_router, workspace_service
from tests.backend.fixtures.sat_store import FixtureSATStore as SATGraphStore


@pytest.fixture
def corpus(tmp_path):
    path = tmp_path / "sat_prov.sqlite3"
    store = SATGraphStore(path)
    markdown = (
        "Ley N° 28970\n"
        "Artículo 1. Objeto\n"
        "El Poder Judicial deberá crear y administrar el REDAM conforme a la Ley N° 27444.\n"
        "Artículo 2. Plazo y prohibición\n"
        "Se prohíbe cobrar tasas en un plazo de 15 días hábiles.\n"
    )
    a1 = markdown.index("Artículo 1.")
    a2 = markdown.index("Artículo 2.")
    spans = [
        ("root", "instrument", 0, len(markdown), None),
        ("art1", "article", a1, a2, "root"),
        ("art2", "article", a2, len(markdown), "root"),
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


@pytest.fixture
def client(corpus, monkeypatch):
    workspace_service.clear_cache()
    monkeypatch.setattr("services.sat_corpus_routes.runtime_sat_store", lambda: corpus.store)
    monkeypatch.setattr(settings, "COHERE_API_KEY", "")

    token = "test-prov-session"
    app = FastAPI()

    async def local_session(request: Request):
        cookie = request.cookies.get("sat_editor_session", "")
        if not secrets.compare_digest(cookie, token):
            raise HTTPException(403, "Unauthorized")
        return "local-reviewer"

    app.dependency_overrides[require_quality_admin] = local_session

    @app.get("/local-session/{access}")
    async def bootstrap(access: str):
        if not secrets.compare_digest(access, token):
            raise HTTPException(403)
        resp = RedirectResponse("/sat-graph/review", status_code=303)
        resp.set_cookie("sat_editor_session", token, httponly=True, samesite="strict", path="/")
        return resp

    app.include_router(review_router)
    app.include_router(provenance_router)

    with TestClient(app) as test_client:
        yield test_client


def test_provenance_routes_enforce_auth_and_csrf_header(client):
    # Unauthenticated -> 403
    assert client.get("/sat-graph/review/provenance/capabilities").status_code == 403
    assert client.post("/sat-graph/review/documents/pe:ley:28970/provenance-graph", json={}).status_code == 403
    assert client.post("/sat-graph/review/provenance/polynomial/parse", json={"expression": "o1"}).status_code == 403

    # Authenticate via cookie
    client.get("/local-session/test-prov-session", follow_redirects=False)

    # Authenticated POST without X-SAT-Review: 1 -> 403
    assert client.post("/sat-graph/review/documents/pe:ley:28970/provenance-graph", json={}).status_code == 403
    assert client.post(
        "/sat-graph/review/documents/pe:ley:28970/provenance-query",
        json={"question": "¿Qué obligaciones hay?"},
    ).status_code == 403
    assert client.post("/sat-graph/review/provenance/polynomial/parse", json={"expression": "o1"}).status_code == 403


def test_provenance_end_to_end_graph_query_ntriples_draft_and_zero_store_writes(client, corpus):
    before_store = corpus.store.export()
    client.get("/local-session/test-prov-session", follow_redirects=False)
    headers = {"X-SAT-Review": "1"}

    # 1. Capabilities
    cap = client.get("/sat-graph/review/provenance/capabilities")
    assert cap.status_code == 200
    cap_data = cap.json()
    assert cap_data["offline_ready"] is True
    assert cap_data["cohere_available"] is False
    assert "SELECT" in cap_data["supported_sparql_features"]
    assert cap_data["templates"]

    # 2. Build deterministic graph
    graph_resp = client.post(
        "/sat-graph/review/documents/pe:ley:28970/provenance-graph",
        json={"mode": "deterministic"},
        headers=headers,
    )
    assert graph_resp.status_code == 200
    gdata = graph_resp.json()
    assert gdata["doc_id"] == "pe:ley:28970"
    assert gdata["cohere_used"] is False
    assert len(gdata["occurrences"]) >= 6
    assert "art1" in gdata["source_units"]
    assert all("parallel_index" in edge for edge in gdata["subgraph"]["edges"])

    # 3. Export RDF-star N-Triples
    nt_resp = client.get("/sat-graph/review/documents/pe:ley:28970/provenance-graph/ntriples")
    assert nt_resp.status_code == 200
    assert "text/plain" in nt_resp.headers["content-type"]
    assert "attachment;" in nt_resp.headers["content-disposition"]
    assert "<< " in nt_resp.text and "textprov/occurrenceOf" in nt_resp.text

    # 4. Run NL query and explicit multi-hop SPARQL query
    nl_resp = client.post(
        "/sat-graph/review/documents/pe:ley:28970/provenance-query",
        json={"question": "¿Qué obligaciones establece la norma?"},
        headers=headers,
    )
    assert nl_resp.status_code == 200
    nl_data = nl_resp.json()
    assert nl_data["nl_compiler"] == "deterministic_template"
    assert len(nl_data["rows"]) >= 1
    row0 = nl_data["rows"][0]
    assert row0["polynomial"] and row0["compact_polynomial"] and row0["npcs_prefix"]
    assert nl_data["occurrences"] and nl_data["source_units"] and nl_data["subgraph"]["edges"]

    # 5. Query against an unsaved draft Edition
    edition = Edition.model_validate(corpus.get("pe:ley:28970")["edition"])
    draft = replace_text(
        TextEdit(
            edition=edition,
            component_id="art2",
            text="Artículo 2. Plazo y prohibición\nSe prohíbe cobrar recargos extraordinarios en un plazo de 10 días hábiles.\n",
        )
    )
    draft_resp = client.post(
        "/sat-graph/review/documents/pe:ley:28970/provenance-query",
        json={"question": "¿Qué prohibiciones existen?", "draft_edition": draft.model_dump()},
        headers=headers,
    )
    assert draft_resp.status_code == 200
    assert any(
        "recargos extraordinarios" in (r["bindings"]["prohibicion"]["value"] if r["bindings"].get("prohibicion") else "")
        for r in draft_resp.json()["rows"]
    )

    # 6. Polynomial parse endpoint (ASCII + SparqlProv Unicode)
    poly_resp = client.post(
        "/sat-graph/review/provenance/polynomial/parse",
        json={"expression": "⊕((⊗ o1, o2,), o1, o1)"},
        headers=headers,
    )
    assert poly_resp.status_code == 200
    pdata = poly_resp.json()
    assert pdata["total_multiplicity"] == 3
    assert "2 · o1" in pdata["infix"]
    assert "2 ·" not in pdata["compact_infix"]
    assert pdata["witness_tokens"] == ["o1", "o2"]

    # Zero writes to SATGraphStore!
    assert corpus.store.export() == before_store


def test_provenance_routes_return_422_for_missing_cohere_key_invalid_sparql_and_404_missing_doc(client):
    client.get("/local-session/test-prov-session", follow_redirects=False)
    headers = {"X-SAT-Review": "1"}

    # Missing COHERE_API_KEY -> 422 (never silently fakes Cohere)
    assert (
        client.post(
            "/sat-graph/review/documents/pe:ley:28970/provenance-graph",
            json={"mode": "hybrid_cohere"},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/sat-graph/review/documents/pe:ley:28970/provenance-query",
            json={"question": "¿Qué obligaciones hay?", "nl_mode": "cohere"},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.get("/sat-graph/review/documents/pe:ley:28970/provenance-graph/ntriples?mode=hybrid_cohere").status_code
        == 422
    )

    # Mutation SPARQL -> 422
    assert (
        client.post(
            "/sat-graph/review/documents/pe:ley:28970/provenance-query",
            json={"sparql": "DELETE WHERE { ?s ?p ?o }"},
            headers=headers,
        ).status_code
        == 422
    )

    # Unknown document -> 404
    assert (
        client.post(
            "/sat-graph/review/documents/pe:ley:999999/provenance-graph",
            json={"mode": "deterministic"},
            headers=headers,
        ).status_code
        == 404
    )
