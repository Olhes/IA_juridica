"""Registro verificable de fechas de publicación, sin promover temporalidad CTV."""
from ingestion.sat_graph.store import canonical, digest
from ingestion.sat_graph.runtime import runtime_sat_store


def main():
    store = runtime_sat_store()
    evidence = {
        'document': 'ley-28970', 'published_on': '2007-01-27',
        'effective_on': '2007-03-13',
        'basis': 'Disposición final tercera: 45 días desde la publicación',
        'source_url': 'https://leyes.congreso.gob.pe/Documentos/Leyes/28970.pdf',
        'scope': 'entrada en vigencia inicial de la ley; no verifica vigencia actual de sus artículos',
    }
    with store._transaction() as db:
        import json
        revisions = [(i, json.loads(p)) for i, p in db.execute("SELECT id,payload FROM sat_nodes WHERE kind='DocumentaryRevision'")]
        matches = [i for i, p in revisions if p['directory'] == evidence['document']]
        if len(matches) != 1:
            raise ValueError('No existe una única revisión documental de la ley')
        identity = 'publication-evidence:' + digest(canonical(evidence))
        store._node(db, identity, 'PublicationEvidence', evidence)
        store._edge(db, matches[0], 'has_publication_evidence', identity, {'source_url': evidence['source_url']})
        extra = [
            ('ley-30364-original', '2015-11-23', '2015-11-24', 'https://www.leyes.congreso.gob.pe/Documentos/2016_2021/ADLP/Ficha_Tecnica_Espanol/30364-FTE.pdf'),
            ('ley-30490', '2016-07-21', '2016-07-22', 'https://leyes.congreso.gob.pe/Documentos/ExpVirPal/Ficha_Tecnica_Espanol/30490-FTE.pdf'),
            ('ley-31464', '2022-05-04', '2022-05-05', 'https://www.leyes.congreso.gob.pe/Documentos/2021_2026/ADLP/Ficha_Tecnica_Espanol/31464-FTE.pdf'),
            ('ds-005-2022-mimp', '2022-04-05', None, 'https://www.pj.gob.pe/wps/wcm/connect/b7200a00469073848e828f76dd7c9e83/DECRETO_SUPREMO_005_2022_MIMP.pdf?CACHEID=b7200a00469073848e828f76dd7c9e83&MOD=AJPERES'),
            ('ds-024-2021-mimp', '2021-07-27', None, 'https://busquedas.elperuano.pe/dispositivo/NL/1976596-2'),
            ('ds-004-2025-mimp', '2025-06-10', None, 'https://www.gob.pe/institucion/mimp/normas-legales/6850857-004-2025-mimp'),
            ('rm-100-2021-mimp', '2021-03-30', None, 'https://apps8.contraloria.gob.pe/SPIC/srvDownload/ViewPDF?CRES_CODIGO=2023CPO390100015&TIPOARCHIVO=ADJUNTO'),
        ]
        for document, published, effective, url in extra:
            matches = [i for i, p in revisions if p['directory'] == document]
            if len(matches) != 1:
                raise ValueError(f'No existe una única revisión de {document}')
            item = {'document': document, 'published_on': published, 'effective_on': effective,
                    'date_status': 'official_source' if effective else 'fecha_vigencia_pendiente',
                    'source_url': url,
                    'scope': 'fecha de la norma inicial; no acredita vigencia actual de cada artículo'}
            ident = 'publication-evidence:' + digest(canonical(item))
            store._node(db, ident, 'PublicationEvidence', item)
            store._edge(db, matches[0], 'has_publication_evidence', ident, {'source_url': url})
    print('Registradas fechas de publicación para 8 documentos; vigencia inicial confirmada para 4.')


if __name__ == '__main__':
    main()
