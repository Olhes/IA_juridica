import pytest

from ingestion.sat_graph.store import SATGraphStore
from retrieval.sat_chat import SATChatRetriever


@pytest.mark.asyncio
async def test_sat_chat_retrieves_attested_ctv_and_abstains_outside_date(tmp_path):
    path = tmp_path / 'graph.sqlite3'
    store = SATGraphStore(path)
    with store._transaction() as db:
        store._node(db, 'work:test', 'Work', {'resource_id': 'pe:ley:28970', 'component': 'test', 'label': 'Artículo 1', 'kind': 'article'})
        store._node(db, 'ctv:test', 'CTV', {'work_id': 'work:test', 'scope': 'PE', 'valid_from': None,
            'valid_to': None, 'snapshot_as_of': '2026-11-12', 'checked_through': '2026-11-12',
            'provenance_state': 'user_attested_snapshot', 'review_id': 'r'})
        store._node(db, 'clv:test', 'CLV', {'language': 'es', 'text': 'Registro de deudores alimentarios morosos',
            'start': 0, 'evidence_id': 'fuente', 'source_url': 'https://example.org'})
        store._edge(db, 'ctv:test', 'has_text', 'clv:test', {})
    adapter = SATChatRetriever(path, '2026-11-12')
    result = await adapter.query_with_rerank('deudores alimentarios')
    assert result['method'] == 'sat'
    assert result['documents'][0]['metadata']['version_id'] == 'ctv:test'
    assert result['documents'][0]['metadata']['retrieval_origin'] == 'sat'
    assert adapter.get_cache_revision() is None
    absent = await SATChatRetriever(path, '2026-11-13').query_with_rerank('deudores alimentarios')
    assert absent['documents'] == []
    current = await SATChatRetriever(path).query_with_rerank('deudores alimentarios')
    assert current['documents'][0]['metadata']['version_id'] == 'ctv:test'
    assert current['sat_as_of'] is None


def test_sat_chat_refuses_to_create_missing_graph(tmp_path):
    with pytest.raises(FileNotFoundError):
        SATChatRetriever(tmp_path / 'missing.sqlite3')


@pytest.mark.asyncio
async def test_explicit_article_walks_eligible_ctv_tree_without_siblings(tmp_path):
    path = tmp_path / "graph.sqlite3"
    store = SATGraphStore(path)
    law = "pe:ley:28970"
    with store._transaction() as db:
        def provision(key, label, kind, text, start, parent=None, *, resource=law, archived=False):
            work, version, clv = (f"{prefix}:{key}" for prefix in ("work", "ctv", "clv"))
            store._node(db, work, "Work", {"resource_id": resource, "component": key,
                                          "kind": kind, "label": label})
            store._node(db, version, "CTV", {"work_id": work, "scope": "PE",
                "provenance_state": "user_attested_snapshot", "snapshot_as_of": "2026-11-12",
                "valid_from": None, "valid_to": None, "checked_through": "2026-11-12",
                "editorial_superseded_by": "replacement" if archived else None, "review_id": "r"})
            store._node(db, clv, "CLV", {"language": "es", "text": text, "start": start,
                "source_url": "https://example.org", "evidence_id": "source"})
            store._edge(db, version, "has_text", clv, {})
            if parent:
                store._edge(db, f"ctv:{parent}", "contains_version", version, {})

        provision("8", "Artículo 8. Registro", "article", "Artículo 8. Registro", 0)
        provision("80", "Artículo 80. Otro", "article", "Artículo equivocado", 100)
        provision("other-law", "Artículo 8. Otro", "article", "Ley equivocada", 0, resource="pe:ley:30364")
        provision("c", "c) Hermano", "inciso", "c) No corresponde", 20, "8")
        provision("d", "d) Supuestos", "inciso", "d) Supuestos\n1. Alfa\n2. Beta", 40, "8")
        provision("d2", "2. Beta", "numeral", "2. Beta", 60, "d")
        provision("d1", "1. Alfa", "numeral", "1. Alfa", 53, "d")
        provision("old", "1. Antiguo", "numeral", "1. Antiguo", 53, "d", archived=True)
        decree = "pe:ds:024-2021-mimp"
        list_text = "- 7.2 Deberes:\n- a. Primero.\n- b. Segundo."
        provision("7", "Artículo 7.- Deberes", "article",
                  f"Artículo 7.- Deberes\n- 7.1 Regla general.\n{list_text}\n- 7.3 Otra regla.",
                  0, resource=decree)
        provision("7.1", "7.1 Regla general.", "numeral", "- 7.1 Regla general.", 22, "7", resource=decree)
        provision("7.2", "7.2 Deberes", "numeral", list_text, 44, "7", resource=decree)
        provision("7.2a", "- a. Primero.", "inciso", "- a. Primero.", 60, "7.2", resource=decree)
        provision("7.2b", "- b. Segundo.", "inciso", "- b. Segundo.", 74, "7.2", resource=decree)
        provision("7.3", "7.3 Otra regla.", "numeral", "- 7.3 Otra regla.", 87, "7", resource=decree)
        provision("law7", "Artículo 7.- Deberes", "article", "Texto distinto de la ley.", 0, resource="pe:ley:30490")
        provision("decree8", "Artículo 8.- Incompleto", "article",
                  "Artículo 8.- Incompleto\n- a. Uno.\n- b. Dos.", 100, resource=decree)
        provision("decree8a", "- a. Uno.", "inciso", "- a. Uno.", 125, "decree8", resource=decree)

    adapter = SATChatRetriever(path)
    question = ("En el artículo 8 de la Ley N.º 28970, ¿cuáles son los supuestos del inciso d)?"
                "\nContexto de preguntas anteriores:\nArtículo 80 de la Ley 30364")
    answer = await adapter.query_with_rerank(question, top_k=1)
    assert answer["sat_reference"]["status"] == "exact"
    assert [d["document_id"] for d in answer["documents"]] == ["work:d"]
    assert answer["verbatim_answer"].endswith("1. Alfa\n2. Beta")
    single = await adapter.query_with_rerank("Numeral 2 del literal d) del art. 8 de la Ley 28970")
    assert [d["content"] for d in single["documents"]] == ["2. Beta"]
    assert single["verbatim_answer"] is None
    for invalid in ("inciso z del artículo 8 de la Ley 28970",
                    "artículos 8 y 80 de la Ley 28970",
                    "inciso d del artículo 8 de la Ley 99999"):
        missing = await adapter.query_with_rerank(invalid)
        assert missing["documents"] == []
        assert missing["sat_reference"]["status"] == "unresolved"

    follow_up = "Dame los literales a. b. c. etc."
    answer = await adapter.query_with_rerank(follow_up, prior_questions=[
        "¿Qué dice el artículo 7 de la Ley 30490?",
        "¿Qué dice el Artículo 7.- Deberes de los integrantes del grupo familiar del DS-024-2021?",
    ])
    assert answer["sat_reference"]["resource_id"] == decree
    assert answer["sat_reference"]["numeral"] == "7.2"
    assert answer["verbatim_answer"].endswith("- a. Primero.\n- b. Segundo.")
    assert [d["document_id"] for d in answer["documents"]] == ["work:7.2"]
    assert answer["documents"][0]["metadata"]["sat_section"]["path"] == [
        "Decreto Supremo 024-2021-MIMP", "Artículo 7", "Numeral 7.2",
    ]
    assert answer["documents"][0]["content"] == list_text
    explicit = await adapter.query_with_rerank("Literal b. del numeral 7.2 del artículo 7 del D.S. 024-2021-MIMP")
    assert [d["document_id"] for d in explicit["documents"]] == ["work:7.2b"]
    incomplete = await adapter.query_with_rerank("Dame los literales del artículo 8 del DS 024-2021-MIMP")
    assert incomplete["sat_reference"]["status"] == "unresolved"
    assert incomplete["documents"] == []
    ambiguous = await adapter.query_with_rerank(follow_up, prior_questions=[
        "Compara el artículo 7 del DS-024-2021 con el artículo 7 de la Ley 30490",
    ])
    assert ambiguous["documents"] == []
