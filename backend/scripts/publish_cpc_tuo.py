"""Importa la edición completa del CPC y la Ley 32006 en SAT; --apply publica."""

from argparse import ArgumentParser
from collections import Counter
from datetime import date
from hashlib import sha256
from pathlib import Path
import re

from ingestion.sat_graph.catalog import load_catalog
from ingestion.sat_graph.official_cpc import CPC, CPC_PDF, CPC_URL, LAW, LAW_PDF, LAW_URL, parse_cpc, parse_law_32006
from ingestion.sat_graph.runtime import runtime_sat_store
from ingestion.source_evidence import SourceEvidence
from services.sat_corpus import CorpusEditor, Edition, OfficialEditionSource, Publication, validate_edition


PDF_DIR = Path(__file__).resolve().parents[1] / "docs" / "sat_reviews" / "published-references"


def _verify_564(cpc_markdown, cpc_components, law_markdown):
    node = next(n for n in cpc_components if n["id"] == "new:cpc-564")
    cpc_text = cpc_markdown[node["start"]:node["end"]]

    def words(text):
        # La cita termina antes de las notas editoriales y las disposiciones de la ley.
        quoted = text.split('“Artículo 564.-', 1)[1].split('”', 1)[0]
        return " ".join(quoted.split()).rstrip(".")

    if words(cpc_text) != words(law_markdown) or "es inimpugnable" not in words(cpc_text):
        raise ValueError("El artículo 564 del TUO diverge de la publicación de la Ley 32006")


def _historical_564(graph):
    """Conservar la Ley 31464, pero no dar su redacción anterior como actual."""
    nodes = {node['id']: node for node in graph['nodes']}
    works = {node['id'] for node in nodes.values() if node['type'] == 'Work'
             and node['resource_id'] == 'pe:ley:31464'}
    versions = {node['id']: node for node in nodes.values() if node['type'] == 'CTV'
                and node['work_id'] in works and not node.get('editorial_superseded_by')}
    children = {identity for identity, node in versions.items() if
                re.match(r'^Artículo 564\b', nodes[node['work_id']]['label'])}
    if not children:
        return ()
    parents = {edge['source'] for edge in graph['edges'] if edge['type'] == 'contains_version'
               and edge['target'] in children and edge['source'] in versions
               and re.match(r'^Artículo 4\b', nodes[versions[edge['source']]['work_id']]['label'])}
    if len(children) != 1 or len(parents) != 1:
        raise ValueError("La cita anterior del 564 tiene una estructura ambigua en Ley 31464")
    return tuple(sorted(children | parents))


def _evidence(pdf, markdown):
    pdf_hash = sha256(pdf).hexdigest()
    encoded = markdown.encode()
    return SourceEvidence(1, f"pdf-sha256-{pdf_hash}", pdf_hash, sha256(encoded).hexdigest(),
                          len(pdf), len(encoded), "unverified")


def publish(store, *, directory=PDF_DIR, apply=False):
    cpc_pdf, law_pdf = [(directory / name).read_bytes() for name in (CPC_PDF, LAW_PDF)]
    cpc_markdown, cpc_components = parse_cpc(cpc_pdf)
    law_markdown, law_components = parse_law_32006(law_pdf)
    _verify_564(cpc_markdown, cpc_components, law_markdown)
    editor = CorpusEditor(store)
    graph = store.export()
    resources = {r['id']: r for r in load_catalog()}
    existing = {doc['id']: doc for doc in editor.list()}
    plans = []
    for rid, pdf_name, url, label_date, pdf, markdown, components in (
        (LAW, LAW_PDF, LAW_URL, date(2024, 4, 24), law_pdf, law_markdown, law_components),
        (CPC, CPC_PDF, CPC_URL, date(2025, 6, 7), cpc_pdf, cpc_markdown, cpc_components),
    ):
        current = editor.get(rid) if rid in existing else None
        evidence = _evidence(pdf, markdown)
        if current and current['evidence_id'] == evidence.evidence_id:
            print(f"{rid}: fuente oficial ya publicada ({current['retrievable']} componentes)")
            continue
        draft = validate_edition(Edition(revision=current['edition']['revision'] if current else "new:official-source",
                                         markdown=markdown, components=components))
        source = OfficialEditionSource(evidence, pdf_name, url, label_date, resources[rid],
                                       historical_quotations=_historical_564(graph) if rid == CPC else (),
                                       amendments=(("new:cpc-564", LAW),) if rid == CPC else ())
        publication = Publication(edition=draft, reason=("Publicar TUO oficial completo y vincular el artículo 564 a la Ley 32006."
                                  if rid == CPC else "Publicar Ley 32006 desde los dos folios de la publicación oficial."))
        plans.append((rid, publication, source))
        print(rid, Counter(c.kind for c in draft.components))
    if apply:
        for rid, publication, source in plans:
            result = editor.apply(rid, publication, "importador-oficial-sat", official=source)
            print(f"{rid}: publicado, {result['retrievable']} componentes recuperables")


def main():
    cli = ArgumentParser(description=__doc__)
    cli.add_argument("--apply", action="store_true", help="publicar; por defecto solo valida y muestra el plan")
    args = cli.parse_args()
    publish(runtime_sat_store(), apply=args.apply)


if __name__ == "__main__":
    main()
