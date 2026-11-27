import pytest

from tests.backend.fixtures.sat_store import FixtureSATStore as SATGraphStore
from retrieval.sat_chat import SATChatRetriever, _expand_ranked_component
from retrieval.sat import SearchPlan
from retrieval.sat_citations import match_article_heading, _marker


def test_untitled_article_can_match_unambiguous_clv_heading():
    class Headings:
        def __init__(self, entries):
            self.entries = entries
        def eligible(self, plan):
            return self.entries
    def article(resource, label, text):
        return {'work': {'kind': 'article', 'label': label, 'resource_id': resource},
                'text': {'text': text}}
    first = article('pe:ley:31464', 'Artículo 170-A', '## Artículo 170-A.- Audiencia única')
    query = 'Cuáles son las reglas para una audiencia única en alimentos?'
    assert match_article_heading(Headings([first]), SearchPlan(query=query), query) == ('pe:ley:31464', '170-a')
    duplicate = article('pe:ley:10000', 'Artículo 44', 'Artículo 44.- Audiencia única')
    assert match_article_heading(Headings([first, duplicate]), SearchPlan(query=query), query) is None
    wrong_number = article('pe:ley:31464', 'Artículo 170-A', 'Artículo 171.- Audiencia única')
    assert match_article_heading(Headings([wrong_number]), SearchPlan(query=query), query) is None


def test_marker_accepts_human_readable_literal_and_inciso_labels():
    assert _marker({'work': {'label': 'Literal a)'}}) == 'a'
    assert _marker({'work': {'label': 'Inciso ñ)'}}) == 'ñ'
    assert _marker({'work': {'label': '- b. Texto'}}) == 'b'


def test_heading_lookup_loads_only_selected_article_and_checks_revision(tmp_path):
    store = SATGraphStore(tmp_path / 'heading.sqlite3')
    resource = 'pe:ley:31464'
    with store._transaction() as db:
        def add(key, kind, label, text, offset, parent=None):
            work, version, clv = (f'{prefix}:{key}' for prefix in ('work', 'ctv', 'clv'))
            store._node(db, work, 'Work', {'resource_id': resource, 'component': key, 'kind': kind, 'label': label})
            store._node(db, version, 'CTV', {'work_id': work, 'scope': 'PE', 'provenance_state': 'user_attested_snapshot',
                'snapshot_as_of': '2026-11-12', 'valid_from': None, 'valid_to': None,
                'checked_through': '2026-11-12', 'review_id': 'r'})
            store._node(db, clv, 'CLV', {'language': 'es', 'text': text, 'start': offset,
                'source_url': 'https://example.org', 'evidence_id': 'source'})
            store._edge(db, version, 'has_text', clv, {})
            if parent:
                store._edge(db, f'ctv:{parent}', 'contains_version', version, {})
        add('3', 'article', 'Artículo 3. Incorporación en el Código', 'Incorporación', 0)
        add('170', 'article', 'Artículo 170-A', '## Artículo 170-A.- Audiencia única\n- a) Uno\n- b) Dos', 20, '3')
        add('a', 'inciso', 'Literal a)', '- a) Uno', 57, '170')
        add('b', 'inciso', 'Literal b)', '- b) Dos', 67, '170')

    graph = store.export()
    class Selective:
        def __init__(self, revision=1):
            self.calls = []
            self.revision = revision
        def chat_heading_snapshot(self):
            self.calls.append('headings')
            return {**graph, 'chat_revision': 1}
        def chat_article_snapshot(self, rid, wid):
            self.calls.append(('article', rid, wid))
            return {**graph, 'chat_revision': self.revision}
        def chat_snapshot(self, resource=None):
            self.calls.append(('global', resource))
            return graph
    query = 'Cuáles son las reglas de la audiencia única?'
    selective = Selective()
    result = SATChatRetriever(selective)._search(query, 5, 30)
    assert selective.calls == ['headings', ('article', resource, 'work:170')]
    assert result['reference']['article'] == '170-a'
    assert 'Artículo 3. Incorporación en el Código' in result['reference']['citation']
    assert result['verbatim_answer'].endswith('- a) Uno\n- b) Dos')
    raced = Selective(revision=2)
    result = SATChatRetriever(raced)._search(query, 5, 30)
    assert raced.calls[-1] == ('global', None)
    assert result['reference']['article'] == '170-a'


def test_retriever_reuse_is_bound_to_snapshot_identity():
    adapter = SATChatRetriever(object())
    first = {'nodes': [], 'edges': []}
    second = {'nodes': [], 'edges': []}
    assert adapter._retriever_for(first) is adapter._retriever_for(first)
    assert adapter._retriever_for(second) is not adapter._retriever_for(first)


def test_expand_structured_article_preserves_identity_and_budget():
    full = 'Artículo 170-A\n- a) ' + 'x' * 1100 + '\n- b) segunda\n- c) tercera'
    item = {'version': {'id': 'v'}, 'work': {'kind': 'article', 'resource_id': 'r'}, 'text': {'id': 't', 'start': 0, 'text': full}}
    child = {'version': {'id': 'child'}, 'work': {'kind': 'inciso', 'resource_id': 'r'}, 'text': {'start': 0, 'text': full[:20]}}
    class Retriever:
        outgoing = {('v', 'contains_version'): ['child']}
        def eligible(self, plan):
            return [item, child]
    def result():
        return {'hits': [{'version_id': 'v', 'content': full[:1000]}]}
    plan = SearchPlan(query='reglas de audiencia', context_bytes=16000)
    expanded = _expand_ranked_component(result(), Retriever(), plan)['hits'][0]
    assert expanded['content'] == full and expanded['end'] == len(full)
    assert expanded['text_sha256'] == __import__('hashlib').sha256(full.encode()).hexdigest()
    small = plan.model_copy(update={'context_bytes': 1000})
    limited = _expand_ranked_component(result(), Retriever(), small)
    assert limited['hits'] == [] and limited['reason'] == 'complete_component_exceeds_budget'
    child['text']['text'] = 'texto incompatible'
    assert _expand_ranked_component(result(), Retriever(), plan)['reason'] == 'inconsistent_component_structure'


def test_context_packing_prioritizes_complete_text_and_deduplicates_graph():
    from collections import defaultdict
    def item(key, text, start=0):
        return {'version': {'id': key}, 'work': {'resource_id': 'r', 'kind': 'article'},
                'text': {'id': 'text:' + key, 'text': text, 'start': start}}
    parent = item('p', 'á' * 600)
    child = item('c', 'á' * 200)
    other = item('o', 'z' * 1000, 2000)
    class Retriever:
        outgoing = defaultdict(list, {('p', 'contains_version'): ['c']})
        def eligible(self, plan):
            return [parent, child, other]
    result = {'hits': [{'version_id': key, 'content': body}
                       for key, body in [('p', 'á' * 100), ('c', 'á' * 50), ('o', 'z' * 100)]]}
    plan = SearchPlan(query='consulta sin palabras especiales', context_bytes=1300)
    packed = _expand_ranked_component(result, Retriever(), plan)
    assert [h['version_id'] for h in packed['hits']] == ['p']
    assert packed['context_bytes'] == 1200  # UTF-8 bytes, not characters.
    assert packed['hits'][0]['content'] == parent['text']['text']
    assert [x['reason'] for x in packed['omitted_components']] == ['structural_overlap', 'complete_component_exceeds_budget']
    assert SearchPlan(query='q').context_bytes == 24000


def test_complete_leaf_between_old_and_new_budget_is_not_truncated():
    from collections import defaultdict
    full = 'contenido ' * 2000
    class Retriever:
        outgoing = defaultdict(list)
        def eligible(self, plan):
            return [{'version': {'id': 'v'}, 'work': {'resource_id': 'r', 'kind': 'article'},
                     'text': {'id': 't', 'text': full, 'start': 15}}]
    result = {'hits': [{'version_id': 'v', 'content': full[:1000]}]}
    plan = SearchPlan(query='explícalo')
    packed = _expand_ranked_component(result, Retriever(), plan)
    assert packed['hits'][0]['content'] == full
    assert packed['hits'][0]['start'] == 15
    assert packed['hits'][0]['end'] == 15 + len(full)
    assert packed['context_bytes'] == 20000
    assert _expand_ranked_component(result, Retriever(), plan.model_copy(update={'context_bytes': 16000}))['state'] == 'abstain'


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
    adapter = SATChatRetriever(store, '2026-11-12')
    result = await adapter.query_with_rerank('deudores alimentarios')
    assert result['method'] == 'sat'
    assert result['documents'][0]['metadata']['version_id'] == 'ctv:test'
    assert result['documents'][0]['metadata']['retrieval_origin'] == 'sat'
    assert adapter.get_cache_revision() is None
    absent = await SATChatRetriever(store, '2026-11-13').query_with_rerank('deudores alimentarios')
    assert absent['documents'] == []
    current = await SATChatRetriever(store).query_with_rerank('deudores alimentarios')
    assert current['documents'][0]['metadata']['version_id'] == 'ctv:test'
    assert current['sat_as_of'] is None


def test_corpus_ready_defaults_to_true_for_stores_without_the_probe(tmp_path):
    """Los fixtures no tienen corpus ausente: solo PostgreSQL puede estar vacío."""
    adapter = SATChatRetriever(SATGraphStore(tmp_path / 'graph.sqlite3'))
    assert adapter.corpus_ready() is True


def test_corpus_ready_reports_an_empty_shared_corpus(tmp_path):
    class EmptyStore(SATGraphStore):
        def is_ready(self):
            return False

    adapter = SATChatRetriever(EmptyStore(tmp_path / 'graph.sqlite3'))
    assert adapter.corpus_ready() is False



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
        provision("cpc96", "Artículo 96.- Audiencia complementaria", "article",
                  "Texto del Código Procesal Civil.", 0, resource="pe:dl:768")
        provision("cna96", "Artículo 96.- Competencia", "article",
                  "Texto del Código de los Niños y Adolescentes.", 0, resource="pe:ley:27337")
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
        provision("13", "Artículo 13.- Lineamientos para el funcionamiento de los CIAM",
                  "article", "Lineamientos:\n- a. Uno.\n- b. Dos.", 150, resource=decree)
        provision("13a", "- a. Uno.", "inciso", "- a. Uno.", 166, "13", resource=decree)
        provision("13b", "- b. Dos.", "inciso", "- b. Dos.", 176, "13", resource=decree)
        provision("14", "Artículo 14.- Funcionamiento de los CIAM",
                  "article", "Otro artículo.", 190, resource=decree)
        provision("law7", "Artículo 7.- Deberes", "article", "Texto distinto de la ley.", 0, resource="pe:ley:30490")
        provision("decree8", "Artículo 8.- Incompleto", "article",
                  "Artículo 8.- Incompleto\n- a. Uno.\n- b. Dos.", 100, resource=decree)
        provision("decree8a", "- a. Uno.", "inciso", "- a. Uno.", 125, "decree8", resource=decree)

    adapter = SATChatRetriever(store)
    for reference in ("Código Procesal Civil", "DL 768", "TUO del CPC", "CPC (Decreto Legislativo 768)"):
        answer = await adapter.query_with_rerank(f"¿Qué dice el artículo 96 del {reference}?")
        assert answer["sat_reference"]["citation"] == "Artículo 96 del Código Procesal Civil (Decreto Legislativo 768)"
        assert [d["document_id"] for d in answer["documents"]] == ["work:cpc96"]
    missing = await adapter.query_with_rerank("¿Qué dice el artículo 568 del Código Procesal Civil?")
    assert missing["documents"] == []
    assert missing["sat_reference"]["status"] == "unresolved"
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
    direct = await adapter.query_with_rerank("Dame los literales del numeral 7.2 del artículo 7 del DS 024-2021-MIMP")
    assert direct["sat_reference"]["status"] == "exact"
    assert direct["verbatim_answer"].endswith("- a. Primero.\n- b. Segundo.")
    explicit = await adapter.query_with_rerank("Literal b. del numeral 7.2 del artículo 7 del D.S. 024-2021-MIMP")
    assert [d["document_id"] for d in explicit["documents"]] == ["work:7.2b"]
    incomplete = await adapter.query_with_rerank("Dame los literales del artículo 8 del DS 024-2021-MIMP")
    assert incomplete["sat_reference"]["status"] == "unresolved"
    assert incomplete["documents"] == []
    ambiguous = await adapter.query_with_rerank(follow_up, prior_questions=[
        "Compara el artículo 7 del DS-024-2021 con el artículo 7 de la Ley 30490",
    ])
    assert ambiguous["documents"] == []
    by_heading = await adapter.query_with_rerank(
        "Por otra parte, cuales son los lineamientos para el funcionamiento de los CIAM?",
        prior_questions=["¿Qué dice el artículo 7 del DS-024-2021?"],
    )
    assert by_heading["sat_reference"]["article"] == "13"
    assert by_heading["verbatim_answer"].endswith("- a. Uno.\n- b. Dos.")


@pytest.mark.asyncio
async def test_sat_chat_uses_voyage_hybrid_dense_and_rerank_and_falls_back_on_error(tmp_path):
    from retrieval.voyage import VoyageError

    store = SATGraphStore(tmp_path / "voyage_chat.sqlite3")
    with store._transaction() as db:
        for key, label, text in (
            ("a1", "Artículo 445°", "Hurto famélico de alimentos en un restaurante."),
            ("a2", "Artículo 149°", "Omisión de prestación de alimentos fijados por juez."),
        ):
            store._node(db, f"work:{key}", "Work", {
                "resource_id": "pe:dl:635", "component": key, "kind": "article", "label": label,
            })
            store._node(db, f"ctv:{key}", "CTV", {
                "work_id": f"work:{key}", "scope": "PE", "provenance_state": "user_attested_snapshot",
                "snapshot_as_of": "2026-11-12", "valid_from": None, "valid_to": None,
                "checked_through": "2026-11-12", "review_id": "r",
            })
            store._node(db, f"clv:{key}", "CLV", {
                "language": "es", "text": text, "start": 0,
                "source_url": "https://example.org", "evidence_id": "source",
            })
            store._edge(db, f"ctv:{key}", "has_text", f"clv:{key}", {})

    calls = []

    class FakeVoyage:
        tpm = 120000

        def embed(self, groups, *, input_type="document"):
            calls.append(("embed", input_type, len(groups)))
            if input_type == "query":
                return [[[0.0, 1.0]]], {"requests": 1, "tokens": 5, "cache_hits": 0}
            vecs = []
            for group in groups:
                vecs.append([[0.0, 1.0] if "Omisión" in t else [1.0, 0.0] for t in group])
            return vecs, {"requests": 1, "tokens": 10, "cache_hits": 0}

        def rerank(self, query, docs, *, top_k=5):
            calls.append(("rerank", len(docs)))
            scored = [(i, 0.95 if "Omisión" in d else 0.1) for i, d in enumerate(docs)]
            return sorted(scored, key=lambda pair: -pair[1])[:top_k], {"requests": 1, "tokens": 12, "cache_hits": 0}

    trace = {}
    adapter = SATChatRetriever(store, provider=FakeVoyage())
    res = await adapter.query_with_rerank("incumplimiento de alimentos", trace=trace)
    assert trace["sat_result"]["strategy"] == "hybrid"
    assert trace["sat_result"]["dense_status"] == "executed"
    assert trace["sat_result"]["rerank_status"] == "executed"
    assert res["documents"][0]["document_id"] == "work:a2"
    assert [c[0] for c in calls] == ["embed", "embed", "rerank"]

    class BrokenVoyage:
        tpm = 120000

        def embed(self, groups, *, input_type="document"):
            raise VoyageError("Cuota local Voyage agotada")

        def rerank(self, query, docs, *, top_k=5):
            raise VoyageError("Cuota local Voyage agotada")

    fallback_trace = {}
    fallback = SATChatRetriever(store, provider=BrokenVoyage())
    fb_res = await fallback.query_with_rerank("incumplimiento de alimentos", trace=fallback_trace)
    assert fb_res["documents"]
    assert fallback_trace["sat_result"]["strategy"] == "metadata"
    assert fallback_trace["sat_result"]["dense_status"] == "not_run"

    class RerankOnlyVoyage(FakeVoyage):
        def embed(self, groups, *, input_type="document"):
            raise VoyageError("429 cooldown on embed")

    rerank_trace = {}
    rr = SATChatRetriever(store, provider=RerankOnlyVoyage())
    rr_res = await rr.query_with_rerank("incumplimiento de alimentos", trace=rerank_trace)
    assert rr_res["documents"][0]["document_id"] == "work:a2"
    assert rerank_trace["sat_result"]["dense_status"] == "not_run"
    assert rerank_trace["sat_result"]["rerank_status"] == "executed"


def test_sat_chat_retriever_uses_zero_copy_only_when_chat_revision_present(tmp_path):
    store = SATGraphStore(tmp_path / "zero_copy.sqlite3")
    with store._transaction() as db:
        store._node(db, "pe:ley:1", "Resource", {"title": "Ley 1"})
        store._node(db, "work:a1", "Work", {"resource_id": "pe:ley:1", "component": "a1", "kind": "article", "label": "Art 1"})
        store._node(db, "ctv:a1", "CTV", {"work_id": "work:a1", "scope": "PE", "provenance_state": "user_attested_snapshot", "snapshot_as_of": "2026-11-12", "valid_from": None, "valid_to": None, "checked_through": "2026-11-12", "review_id": "r"})
        store._node(db, "clv:a1", "CLV", {"language": "es", "text": "Texto", "start": 0, "source_url": "https://example.org", "evidence_id": "e"})
        store._edge(db, "ctv:a1", "has_text", "clv:a1", {})

    chat = SATChatRetriever(store)
    raw_snap = store.export()
    copied = chat._retriever_for(raw_snap)
    assert copied.snapshot is not raw_snap
    assert not copied.revision.startswith("chat:")

    rev_snap = {**store.export(), "chat_revision": 7}
    reused = chat._retriever_for(rev_snap)
    assert reused.snapshot is rev_snap
    assert reused.revision == "chat:7"


def test_prune_superseded_chat_graph_drops_superseded_ctvs_and_orphan_clvs():
    from ingestion.sat_graph.surreal import _prune_superseded_chat_graph

    nodes = [
        {"id": "pe:ley:1", "type": "Resource", "title": "Ley 1"},
        {"id": "work:a1", "type": "Work", "resource_id": "pe:ley:1", "kind": "article"},
        {"id": "ctv:old", "type": "CTV", "work_id": "work:a1", "editorial_superseded_by": "ctv:new"},
        {"id": "ctv:new", "type": "CTV", "work_id": "work:a1"},
        {"id": "clv:old", "type": "CLV", "text": "old text"},
        {"id": "clv:new", "type": "CLV", "text": "new text"},
    ]
    edges = [
        {"id": "e1", "source": "ctv:old", "type": "has_text", "target": "clv:old", "evidence": {}},
        {"id": "e2", "source": "ctv:new", "type": "has_text", "target": "clv:new", "evidence": {}},
        {"id": "e3", "source": "ctv:old", "type": "contains_version", "target": "ctv:new", "evidence": {}},
    ]

    kept_nodes, kept_edges = _prune_superseded_chat_graph(nodes, edges)
    assert {n["id"] for n in kept_nodes} == {"pe:ley:1", "work:a1", "ctv:new", "clv:new"}
    assert [e["id"] for e in kept_edges] == ["e2"]


