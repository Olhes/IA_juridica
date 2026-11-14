"""Publish user-attested documentary editions as point-in-time CTV snapshots.

These have no verified legal interval. They are eligible only on snapshot_as_of.
"""
import argparse
import json
from collections import Counter
from datetime import date

from ingestion.sat_graph.store import SATGraphStore, canonical, digest, work_id
from ingestion.sat_graph.runtime import runtime_sat_store

RESOURCES = {
    'ley-30364-original': 'pe:ley:30364', 'ley-28970': 'pe:ley:28970',
    'ley-30490': 'pe:ley:30490', 'ley-31464': 'pe:ley:31464',
    'ds-004-2025-mimp': 'pe:ds:004-2025-mimp', 'ds-005-2022-mimp': 'pe:ds:005-2022-mimp',
    'ds-024-2021-mimp': 'pe:ds:024-2021-mimp', 'rm-100-2021-mimp': 'pe:rm:100-2021-mimp',
}


def publish(store, as_of):
    when = date.fromisoformat(as_of).isoformat()
    with store._transaction() as db:
        rows = db.execute("SELECT id,kind,payload FROM sat_nodes WHERE kind IN ('DocumentaryRevision','DocumentaryComponent')").fetchall()
        records = [(i, k, json.loads(p)) for i, k, p in rows]
        if any(p.get('previous_revision') for _, k, p in records if k == 'DocumentaryRevision'):
            raise ValueError('El corpus tiene correcciones editoriales: use el editor SAT para no reemplazarlas')
        revisions = [(i, p) for i, k, p in records if k == 'DocumentaryRevision']
        counts = Counter(p['directory'] for _, p in revisions)
        if set(counts) != set(RESOURCES) or any(n != 1 for n in counts.values()):
            raise ValueError('Se requiere exactamente una revisión por cada fuente aprobada')
        revs = dict(revisions)
        components = [(i, p) for i, k, p in records if k == 'DocumentaryComponent']
        ids = {}
        for identity, node in components:
            revision = revs[node['revision_id']]
            resource_id = RESOURCES[revision['directory']]
            resource = store._get(db, resource_id, 'Resource')
            component = 'doc-' + digest(node['source_node_id'])
            wid = work_id(resource_id, component)
            text = revision['markdown'][node['start']:node['end']]
            if digest(text) != node['text_sha256'] or not text:
                raise ValueError('Hash de texto documental incorrecto')
            vid = 'ctv-snapshot:' + digest(canonical([wid, when, node['text_sha256']]))
            tid = 'clv-snapshot:' + digest(canonical([vid, 'es', node['text_sha256']]))
            audit = {'evidence_id': revision['evidence_id'], 'source_url': resource['url'],
                     'review_id': revision['review_hash'], 'reviewer': 'usuario: verificación por abogadas declarada',
                     'rule': 'user-attested-point-in-time-v1', 'start': node['start'], 'end': node['end'],
                     'text_sha256': node['text_sha256'], 'documentary_revision': node['revision_id']}
            store._node(db, wid, 'Work', {'resource_id': resource_id, 'component': component, 'label': node['label'], 'kind': node['kind']})
            store._node(db, vid, 'CTV', {'work_id': wid, 'scope': 'PE', 'valid_from': None, 'valid_to': None,
                        'checked_through': when, 'snapshot_as_of': when, 'provenance_state': 'user_attested_snapshot',
                        'text_review_state': revision.get('text_review_state'), **audit})
            store._node(db, tid, 'CLV', {'language': 'es', 'text': text, **audit})
            for source, predicate, target in ((vid, 'version_of', wid), (vid, 'has_text', tid),
                                               (tid, 'evidenced_by', revision['evidence_id']),
                                               (wid, 'instrument', resource_id),
                                               (vid, 'derived_from_documentary', identity)):
                store._edge(db, source, predicate, target, audit)
            ids[identity] = (wid, vid)
        for parent, child in db.execute("SELECT source,target FROM sat_edges WHERE predicate='documentary_has_part'").fetchall():
            if parent not in ids or child not in ids:
                raise ValueError('Jerarquía documental incompleta')
            pw, pv = ids[parent]; cw, cv = ids[child]
            audit = {'rule': 'user-attested-point-in-time-v1', 'snapshot_as_of': when}
            store._edge(db, pw, 'has_part', cw, audit)
            store._edge(db, pv, 'contains_version', cv, audit)
        store._reject_cycles(db, 'has_part')
        store._reject_cycles(db, 'contains_version')
        store._validate_intervals(db)
    return {'documents': len(revisions), 'ctv_count': len(ids), 'snapshot_as_of': when}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--as-of', required=True, help='Fecha ISO de la declaración del usuario')
    args = parser.parse_args()
    print(json.dumps(publish(runtime_sat_store(), args.as_of)))


if __name__ == '__main__':
    main()
