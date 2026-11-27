import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ingestion.sat_graph.store import digest
from tests.backend.fixtures.sat_store import FixtureSATStore as SATGraphStore
from retrieval.sat import SATRetriever, SearchPlan
from retrieval.sat_chat import SATChatRetriever
from services.sat_corpus import CorpusEditor, Edition, Publication, TextEdit, Conflict, replace_text, validate_edition


@pytest.fixture
def corpus(tmp_path):
    path = tmp_path / "sat.sqlite3"
    store = SATGraphStore(path)
    markdown = "Ley de prueba\nArtículo 1. Alimentos\na) Protección a la niñez.\nArtículo 2. Registro.\n"
    spans = [("root", "instrument", 0, len(markdown), None),
             ("art1", "article", markdown.index("Artículo 1"), markdown.index("Artículo 2"), "root"),
             ("inciso", "inciso", markdown.index("a)"), markdown.index("Artículo 2"), "art1"),
             ("art2", "article", markdown.index("Artículo 2"), len(markdown), "root")]
    with store._transaction() as db:
        store._node(db, "source", "Source", {})
        db.execute("INSERT INTO sat_documents VALUES (?,?,'reviewed')", ("source", markdown))
        store._node(db, "revision", "DocumentaryRevision", {"directory": "ley-28970", "evidence_id": "source",
            "markdown": markdown, "markdown_sha256": digest(markdown), "review_hash": "original"})
        for identity, kind, start, end, parent in spans:
            audit = {"start": start, "end": end, "text_sha256": digest(markdown[start:end]),
                     "evidence_id": "source", "review_id": "original", "source_url": "https://example.org"}
            store._node(db, identity, "DocumentaryComponent", {"revision_id": "revision", "source_node_id": identity,
                "label": identity, "kind": kind, **audit})
            store._node(db, "w:"+identity, "Work", {"resource_id": "pe:ley:28970", "component": identity,"label":identity,"kind":kind})
            store._node(db, "v:"+identity, "CTV", {"work_id": "w:"+identity,"scope":"PE","valid_from":None,"valid_to":None,
                "checked_through":"2026-11-12","snapshot_as_of":"2026-11-12","provenance_state":"user_attested_snapshot",
                "documentary_revision":"revision",**audit})
            store._node(db, "t:"+identity, "CLV", {"language":"es","text":markdown[start:end],**audit})
            store._edge(db,"v:"+identity,"has_text","t:"+identity,{})
            store._edge(db,"v:"+identity,"derived_from_documentary",identity,{})
            if parent:
                store._edge(db,parent,"documentary_has_part",identity,{})
                store._edge(db,"w:"+parent,"has_part","w:"+identity,{})
                store._edge(db,"v:"+parent,"contains_version","v:"+identity,{})
    return CorpusEditor(store)


def edited(corpus):
    edition = Edition.model_validate(corpus.get("pe:ley:28970")["edition"])
    return replace_text(TextEdit(edition=edition, component_id="inciso", text="a) Protección integral a la niñez ñ y 😀.\n"))


@pytest.mark.parametrize("official_id,expected_id,expected_count", [
    ("pe:ley:31464", "pe:ley:31464", 3),
    ("pe:ley:28970", "local:documentary:test", 0),
])
def test_candidate_publication_is_explicit_and_does_not_overwrite(corpus, official_id, expected_id, expected_count):
    from services.sat_corpus import Conflict
    original = corpus.get("pe:ley:28970")["edition"]
    edition = Edition.model_validate({**original, "revision": "parse:test"})
    candidate = {"id": "candidate:test", "title": "PDF de prueba", "edition": edition.model_dump(),
                 "editable": True, "versions": [], "official_id": official_id,
                 "reference_only": False, "evidence_id": "source", "pdf_name": "test.pdf",
                 "source": {"markdown_sha256": digest(edition.markdown)}, "source_url": "https://example.org"}
    publication = Publication(edition=edition, reason="Revisión explícita")
    result = corpus.apply(candidate["id"], publication, "test", candidate=candidate)
    assert result["id"] == expected_id
    assert result["retrievable"] == expected_count
    assert result["origin_candidate"] == candidate["id"]
    assert corpus.get("pe:ley:28970")["edition"] == original
    with pytest.raises(Conflict, match="ya fue publicado"):
        corpus.apply(candidate["id"], publication, "test", candidate=candidate)


def test_publication_updates_markdown_ctv_clv_ancestors_and_live_chat(corpus):
    initial = corpus.store.export()
    edition = edited(corpus)
    new = corpus.apply("pe:ley:28970", Publication(edition=edition,reason="Cotejo contra PDF"), "test-human")
    assert new["editable"] and new["retrievable"] == 3
    assert len(new["history"]) == 1
    assert "previous_edition" not in new["history"][0]
    assert "integral" in new["edition"]["markdown"]
    graph = corpus.store.export()
    current = SATRetriever(graph).eligible(SearchPlan(query="niñez"))
    assert len(current) == 3
    assert {x["work"]["id"] for x in current} == {"w:art1", "w:inciso", "w:art2"}
    for item in current:
        text = item["text"]
        assert text["text"] == new["edition"]["markdown"][text["start"]:text["end"]]
        assert digest(text["text"]) == text["text_sha256"]
    assert "integral" in next(x["text"]["text"] for x in current if x["work"]["id"] == "w:art1")
    assert all(v["valid_from"] is None for v in graph["nodes"] if v["type"] == "CTV")
    historical = SATRetriever(graph).eligible(SearchPlan(query="niñez", as_of="2026-11-12"))
    assert {i["version"]["id"] for i in historical} == {i["version"]["id"] for i in current}
    with corpus.store._reader() as db:
        assert db.execute("SELECT markdown FROM sat_documents WHERE evidence_id='source'").fetchone()[0] != edition.markdown
    old_texts = {n["id"]: n for n in initial["nodes"] if n["type"] == "CLV"}
    assert all(n == old_texts[n["id"]] for n in graph["nodes"] if n["id"] in old_texts)
    result = asyncio.run(SATChatRetriever(corpus.store).query_with_rerank("protección integral niñez"))
    assert any("integral" in d["content"] for d in result["documents"])
    # Further changes work; a stale browser cannot overwrite them.
    with pytest.raises(Conflict):
        corpus.apply("pe:ley:28970", Publication(edition=edition,reason="Borrador viejo"), "other")
    second = Edition.model_validate(new["edition"])
    second.components[1].label = "Etiqueta corregida"
    again = corpus.apply("pe:ley:28970", Publication(edition=second,reason="Etiqueta correcta"), "test-human")
    assert len(again["history"]) == 2 and again["retrievable"] == 3


def test_cycles_invalid_spans_and_foreign_ids_never_change_graph(corpus):
    before = corpus.store.export()
    for case in ("cycle", "span", "foreign"):
        edition = Edition.model_validate(corpus.get("pe:ley:28970")["edition"])
        if case == "cycle": edition.components[0].parent_id = edition.components[0].id
        if case == "span": edition.components[1].end = len(edition.markdown)+1
        if case == "foreign": edition.components[1].id = "someone-elses-id"
        with pytest.raises(ValueError):
            corpus.apply("pe:ley:28970", Publication(edition=edition,reason="No aplicar"), "test")
        assert corpus.store.export() == before


def test_add_remove_reparent_changes_real_membership(corpus):
    edition = Edition.model_validate(corpus.get("pe:ley:28970")["edition"])
    inciso = next(n for n in edition.components if n.id == "inciso")
    inciso.parent_id = "root"
    added = inciso.model_copy(update={"id":"new:extra","label":"Inciso detectado"})
    edition.components.append(added)
    edition.components = [n for n in edition.components if n.id != "art2"]
    result = corpus.apply("pe:ley:28970", Publication(edition=edition,reason="Corrige estructura"), "test")
    assert result["components"] == 4 and result["retrievable"] == 3
    graph = corpus.store.export()
    assert any(e["type"] == "has_part" and e["source"] == "w:root" and e["target"] == "w:inciso" for e in graph["edges"])
    assert not any(e["type"] == "has_part" and e["source"] == "w:art1" and e["target"] == "w:inciso" for e in graph["edges"])
    assert "Artículo 2. Registro" in result["edition"]["markdown"]  # removing a node never destroys the source


def test_preview_unicode_boundaries_and_crossing_children(corpus):
    edition = edited(corpus)
    assert "ñ y 😀" in edition.markdown
    validate_edition(edition)
    root = next(n for n in edition.components if n.id == "root")
    assert root.end == len(edition.markdown)
    with pytest.raises(ValueError, match="límite"):
        replace_text(TextEdit(edition=edition, component_id="root", text="Borrar todo el documento"))


def test_preview_cleans_large_root_without_changing_child_text():
    prefix = "x" * 240_000
    garbage = "BASURA OCR\n"
    body = "Artículo 1. Texto conservado."
    edition = Edition(revision="test", markdown=prefix + garbage + body, components=[
        {"id": "root", "label": "Norma", "kind": "document", "start": 0, "end": len(prefix + garbage + body)},
        {"id": "child", "label": "Artículo 1", "kind": "article", "parent_id": "root",
         "start": len(prefix + garbage), "end": len(prefix + garbage + body)},
    ])
    result = replace_text(TextEdit(edition=edition, component_id="root", text=prefix + body))
    assert result.markdown == prefix + body
    root, child = result.components
    assert root.end == len(result.markdown)
    assert child.start == len(prefix)
    assert result.markdown[child.start:child.end] == body


def test_preview_removes_deleted_branch_and_keeps_remaining_sibling(corpus):
    edition = Edition.model_validate(corpus.get("pe:ley:28970")["edition"])
    chapter = next(n for n in edition.components if n.id == "art1")
    text = edition.markdown[:chapter.start] + edition.markdown[chapter.end:]
    result = replace_text(TextEdit(edition=edition, component_id="root", text=text))
    assert result.markdown == text
    assert {n.id for n in result.components} == {"root", "art2"}
    sibling = next(n for n in result.components if n.id == "art2")
    assert sibling.start == chapter.start
    assert text[sibling.start:sibling.end] == edition.markdown[chapter.end:]


def test_transaction_rolls_back_late_failure(corpus, monkeypatch):
    before = corpus.store.export()
    def reject(*args): raise ValueError("simulated failure")
    monkeypatch.setattr(corpus.store, "_reject_cycles", reject)
    with pytest.raises(ValueError):
        corpus.apply("pe:ley:28970", Publication(edition=edited(corpus),reason="No publicar"), "test")
    assert corpus.store.export() == before


@pytest.fixture
def client(corpus, monkeypatch):
    from config.settings import settings
    from sat_review_app import create_local_app
    monkeypatch.setattr("services.sat_corpus_routes.runtime_sat_store", lambda: corpus.store)
    with TestClient(create_local_app("test-local-capability")) as client:
        yield client


def test_http_auth_and_canonical_contract(client, corpus):
    assert client.get("/sat-graph/review").status_code == 200
    assert client.get("/sat-graph/review/documents").status_code == 403
    assert client.get("/sat-graph/api/items/w:art1").status_code == 403
    assert client.post("/sat-graph/review/preview", json={}).status_code == 403
    assert client.get("/local-session/wrong").status_code == 403
    response = client.get("/local-session/test-local-capability", follow_redirects=False)
    assert "HttpOnly" in response.headers["set-cookie"] and "SameSite=strict" in response.headers["set-cookie"]
    base = "/sat-graph/api"
    item = client.get(base+"/items/w:art1").json()
    assert item["typeId"] == "article" and item["parentId"] == "w:root"
    assert client.get(base+"/items/w:root/hierarchy?depth=1").json() == ["w:art1", "w:art2"]
    assert set(client.get(base+"/items/w:root/hierarchy").json()) == {"w:art1", "w:art2", "w:inciso"}
    assert client.get(base+"/versions/v:art1/text-units?language=en").json() == []
    assert client.get(base+"/versions/v:art1/text-units?aspects=summary").json() == []
    assert client.get(base+"/versions/absent/text-units").status_code == 404
    assert client.get(base+"/versions/v:art1").json()["validityInterval"] == [None,None]
    texts = client.post(base+"/text-units/batch-get",json={"versionIds":["v:art1","v:art2"],"language":"es"}).json()
    assert len(texts) == 2 and texts[0]["sourceType"] == "Version"
    assert client.post(base+"/text-units/batch-get",json={"versionIds":["absent"],"language":"es"}).status_code == 404
    assert client.post(base+"/items/batch-get",json={"ids":["w:art1","missing"]}).json() == [item]
    assert client.get(base+"/meta/implementation-guide").json()["conformance"] == "documented-subset"
    assert client.get("/sat-graph/review/documents").json()["documents"][0]["components"] == 4
    body = {"edition":edited(corpus).model_dump(),"reason":"Corregido desde HTTP"}
    endpoint = "/sat-graph/review/documents/pe:ley:28970"
    assert client.post(endpoint,json=body).status_code == 403
    assert client.post(endpoint,json=body,headers={"X-SAT-Review":"1"}).status_code == 200
    assert client.post(endpoint,json=body,headers={"X-SAT-Review":"1"}).status_code == 409
    assert "integral" in client.get(endpoint+"/markdown").text
    assert client.get(endpoint+"/pdf").status_code == 422


def test_core_entities_match_vendored_upstream_schemas(client):
    import yaml
    import jsonschema
    # OpenAPI 3.0 nullable is converted to JSON Schema's explicit null union.
    path = Path(__file__).resolve().parents[3] / "docs/sat-api-upstream/openapi-bundled.yaml"
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    def convert(value):
        if isinstance(value,list): return [convert(x) for x in value]
        if not isinstance(value,dict): return value
        out={k:convert(v) for k,v in value.items() if k!="nullable"}
        if value.get("nullable") and "type" in out: out["type"]=[out["type"],"null"]
        if value.get("nullable") and "$ref" in out: out={"anyOf":[out,{"type":"null"}]}
        return out
    spec=convert(spec)
    client.get("/local-session/test-local-capability")
    for kind, endpoint in [("Item","items/w:art1"),("Version","versions/v:art1"),("TextUnit","text-units/t:art1")]:
        schema={"$ref":"#/components/schemas/"+kind,"components":spec["components"]}
        jsonschema.validate(client.get("/sat-graph/api/"+endpoint).json(),schema)


def test_canonical_graph_links_are_immutable_during_concurrent_reads(corpus):
    from services.sat_api import CanonicalGraph

    cg = CanonicalGraph(corpus.store.export())
    keys_before = set(cg.links.keys())
    # Querying a leaf CTV (no contains_version edges) must never mutate cg.links.
    assert cg.children("v:inciso", versions=True) == []
    assert set(cg.links.keys()) == keys_before
    for _key in cg.links:
        assert cg.children("v:art2", versions=True) == []


def test_sat_review_app_default_port_avoids_backend_and_surrealdb():
    from sat_review_app import DEFAULT_PORT

    assert DEFAULT_PORT not in {8000, 8010}
    assert DEFAULT_PORT == 8011


def test_document_projects_readonly_tree_from_ctvs_when_documentary_components_pruned():
    from services import sat_corpus

    graph = {
        "nodes": [
            {"id": "pe:dl:1377", "type": "Resource", "title": "DL 1377"},
            {"id": "rev:1", "type": "DocumentaryRevision", "markdown": "", "directory": "dl-1377"},
            {"id": "work:tit1", "type": "Work", "resource_id": "pe:dl:1377", "kind": "titulo", "label": "TÍTULO I"},
            {"id": "work:art1", "type": "Work", "resource_id": "pe:dl:1377", "kind": "article", "label": "Artículo 1"},
            {"id": "ctv:tit1", "type": "CTV", "work_id": "work:tit1", "scope": "PE", "provenance_state": "user_attested_snapshot", "documentary_revision": "rev:1", "start": 0, "end": 20},
            {"id": "ctv:art1", "type": "CTV", "work_id": "work:art1", "scope": "PE", "provenance_state": "user_attested_snapshot", "documentary_revision": "rev:1", "start": 21, "end": 80},
            {"id": "clv:tit1", "type": "CLV", "language": "es", "text": "TÍTULO I"},
            {"id": "clv:art1", "type": "CLV", "language": "es", "text": "Artículo 1. Objeto."},
        ],
        "edges": [
            {"id": "e1", "source": "ctv:tit1", "type": "has_text", "target": "clv:tit1", "evidence": {}},
            {"id": "e2", "source": "ctv:art1", "type": "has_text", "target": "clv:art1", "evidence": {}},
            {"id": "e3", "source": "ctv:tit1", "type": "contains_version", "target": "ctv:art1", "evidence": {}},
        ],
    }

    doc = sat_corpus.document(graph, "pe:dl:1377")
    assert doc["editable"] is False
    comps = {c["id"]: c for c in doc["edition"]["components"]}
    assert set(comps) == {"ctv:tit1", "ctv:art1"}
    assert comps["ctv:tit1"]["parent_id"] is None
    assert comps["ctv:art1"]["parent_id"] == "ctv:tit1"
    assert {v["component_id"] for v in doc["versions"]} == {"ctv:tit1", "ctv:art1"}

