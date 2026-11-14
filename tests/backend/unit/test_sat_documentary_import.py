import hashlib
import json

import pytest

from ingestion.sat_graph.import_documentary import import_one
from tests.backend.fixtures.sat_store import FixtureSATStore as SATGraphStore
from retrieval.sat import SATRetriever, SearchPlan


def test_import_preserves_corrected_spans_and_rejects_tampering(tmp_path):
    directory = tmp_path / "review"
    directory.mkdir()
    pdf = b"test pdf"
    original = "Art 50. text\n"
    corrected = "Art 5. text\n"
    sha = lambda value: hashlib.sha256(value).hexdigest()
    (directory / "source.pdf").write_bytes(pdf)
    (directory / "source.md").write_bytes(original.encode())
    (directory / "source.corrected.md").write_bytes(corrected.encode())
    (directory / "text-corrections.json").write_text(json.dumps({
        "original_sha256": sha(original.encode()), "corrected_sha256": sha(corrected.encode()),
        "changes": [{"start": 4, "end": 6, "original": "50", "replacement": "5"}],
    }), encoding="utf-8")
    (directory / "structure-review.json").write_text(json.dumps({
        "review_state": "user_approved_structure",
        "source_sha256": {"source.pdf": sha(pdf), "source.md": sha(original.encode())},
        "nodes": [{"id": "x", "parent_id": None, "kind": "article", "label": "Art 5",
                   "start": 0, "end": len(original), "source_span_sha256": sha(original.encode())}],
    }), encoding="utf-8")
    store = SATGraphStore(tmp_path / "test.sqlite3")
    result = import_one(store, directory)
    assert import_one(store, directory) == result
    with store._reader() as db:
        payload = json.loads(db.execute("SELECT payload FROM sat_nodes WHERE kind='DocumentaryComponent'").fetchone()[0])
        assert payload["end"] == len(corrected)
        assert payload["text_sha256"] == sha(corrected.encode())
        assert db.execute("SELECT count(*) FROM sat_nodes WHERE kind='CTV'").fetchone()[0] == 0
    (directory / "source.corrected.md").write_text("altered", encoding="utf-8")
    with pytest.raises(ValueError):
        import_one(store, directory)


def test_documentary_search_is_explicit_and_not_reviewed():
    text = 'Registro de deudores alimentarios morosos'
    sha = hashlib.sha256(text.encode()).hexdigest()
    snapshot = {'nodes': [
        {'id': 'pe:ley:28970', 'type': 'Resource', 'title': 'Ley 28970', 'url': 'https://example.org'},
        {'id': 'revision', 'type': 'DocumentaryRevision', 'directory': 'ley-28970',
         'markdown': text, 'evidence_id': 'source', 'review_hash': 'review'},
        {'id': 'part', 'type': 'DocumentaryComponent', 'revision_id': 'revision', 'kind': 'article',
         'start': 0, 'end': len(text), 'text_sha256': sha, 'source_node_id': 'article', 'label': 'Artículo 1'},
    ], 'edges': []}
    retriever = SATRetriever(snapshot)
    p = {'query': 'deudores alimentarios', 'as_of': '2026-11-12'}
    assert retriever.search(SearchPlan(**p))['state'] == 'abstain'
    result = retriever.search(SearchPlan(**p, include_documentary=True))
    assert result['state'] == 'retrieved'
    assert result['hits'][0]['content'] == text
    assert result['hits'][0]['provenance_state'] == 'assumed_current_documentary'
    assert result['hits'][0]['valid_from'] is None


def test_attested_ctv_only_resolves_on_snapshot_date():
    snapshot = {'nodes': [
        {'id': 'r', 'type': 'Resource', 'title': 'Norma'},
        {'id': 'w', 'type': 'Work', 'kind': 'article', 'resource_id': 'r', 'component': 'a', 'label': 'Artículo'},
        {'id': 'v', 'type': 'CTV', 'work_id': 'w', 'scope': 'PE', 'valid_from': None, 'valid_to': None,
         'checked_through': '2026-11-12', 'snapshot_as_of': '2026-11-12',
         'provenance_state': 'user_attested_snapshot', 'review_id': 'review'},
        {'id': 't', 'type': 'CLV', 'language': 'es', 'text': 'Pensión de alimentos',
         'start': 0, 'evidence_id': 'source', 'source_url': 'https://example.org'},
    ], 'edges': [{'id': 'e', 'source': 'v', 'target': 't', 'type': 'has_text'}]}
    retriever = SATRetriever(snapshot)
    result = retriever.search(SearchPlan(query='alimentos', as_of='2026-11-12'))
    assert result['hits'][0]['provenance_state'] == 'user_attested_snapshot'
    assert result['hits'][0]['valid_from'] is None
    assert retriever.search(SearchPlan(query='alimentos', as_of='2026-11-11'))['state'] == 'abstain'
    assert retriever.search(SearchPlan(query='alimentos', as_of='2026-11-13'))['state'] == 'abstain'


def test_current_selects_latest_snapshot_and_rejects_ties():
    snapshot = {'nodes': [
        {'id': 'r', 'type': 'Resource', 'title': 'Norma'},
        {'id': 'w', 'type': 'Work', 'kind': 'article', 'resource_id': 'r', 'component': 'a', 'label': 'Artículo'},
    ], 'edges': []}
    for vid, day, content in [('old', '2020-01-01', 'alimentos anterior'), ('new', '2026-11-12', 'alimentos vigente')]:
        snapshot['nodes'].extend([
            {'id': vid, 'type': 'CTV', 'work_id': 'w', 'scope': 'PE', 'valid_from': None, 'valid_to': None,
             'checked_through': day, 'snapshot_as_of': day, 'provenance_state': 'user_attested_snapshot', 'review_id': 'r'},
            {'id': 't' + vid, 'type': 'CLV', 'language': 'es', 'text': content, 'start': 0, 'evidence_id': 'e', 'source_url': 's'},
        ])
        snapshot['edges'].append({'id': 'e' + vid, 'source': vid, 'target': 't' + vid, 'type': 'has_text'})
    plan = SearchPlan(query='alimentos')
    result = SATRetriever(snapshot).search(plan)
    assert [h['version_id'] for h in result['hits']] == ['new']
    assert result['as_of'] is None
    snapshot['nodes'][-2]['valid_to'] = '2027-01-01'
    assert SATRetriever(snapshot).search(plan)['state'] == 'abstain'
    snapshot['nodes'][-2]['valid_to'] = None
    duplicate = dict(snapshot['nodes'][-2], id='duplicate')
    snapshot['nodes'].append(duplicate)
    assert SATRetriever(snapshot).search(plan)['state'] == 'abstain'
