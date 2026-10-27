"""Operación local y offline: catálogo, stage, borrador, revisión y exportación."""

import argparse
import json
from pathlib import Path

from ingestion.source_evidence import persist_source_evidence
from .contracts import ReviewManifest
from .store import SATGraphStore, canonical

DEFAULT_DB = Path(__file__).resolve().parents[2] / "docs" / "sat_graph.sqlite3"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument(
        "--output", type=Path, help="JSON UTF-8 nuevo; no sobrescribe archivos"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "catalog", help="Sembrar recursos, sin descargar ni validar normas"
    )
    commands.add_parser("export", help="Exportar grafo JSON")
    stage = commands.add_parser(
        "stage", help="Registrar PDF y su Markdown ya convertido"
    )
    stage.add_argument("--pdf", type=Path, required=True)
    stage.add_argument("--markdown", type=Path, required=True)
    stage.add_argument(
        "--docling-json",
        type=Path,
        help="JSON del mismo DoclingDocument que produjo el Markdown",
    )
    stage.add_argument(
        "--documentary-review",
        type=Path,
        help="Correcciones estructurales con hashes; NO aprueba normas ni vigencia",
    )
    structure = commands.add_parser(
        "structure", help="AST candidato y evidencia Docling; no aprueba normas"
    )
    structure.add_argument("--evidence-id", required=True)
    structure.add_argument("--parse-id")
    draft = commands.add_parser(
        "draft", help="Borrador NO aprobable hasta completar revisión"
    )
    draft.add_argument("--evidence-id", required=True)
    draft.add_argument("--resource-id", required=True)
    review = commands.add_parser(
        "review", help="Aplicar manifiesto revisado por una persona"
    )
    review.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)
    store = SATGraphStore(args.db)
    if args.command == "stage":
        markdown = args.markdown.read_bytes().decode("utf-8")
        evidence = persist_source_evidence(
            args.pdf, args.markdown, markdown, args.db.parent / "source_evidence"
        )
        layout = (
            json.loads(args.docling_json.read_text(encoding="utf-8"))
            if args.docling_json
            else None
        )
        documentary_review = (
            json.loads(args.documentary_review.read_text(encoding="utf-8"))
            if args.documentary_review
            else None
        )
        result = store.stage(
            evidence, markdown, layout, documentary_review=documentary_review
        )
    elif args.command == "structure":
        result = store.structure(args.evidence_id, args.parse_id)
    elif args.command == "draft":
        result = store.draft(args.evidence_id, args.resource_id)
    elif args.command == "review":
        manifest = ReviewManifest.model_validate(
            json.loads(args.manifest.read_text(encoding="utf-8"))
        )
        result = store.review(manifest)
    elif args.command == "catalog":
        graph = store.export()
        result = {
            "engine": "sat",
            "database": str(args.db.resolve()),
            "resource_count": graph["resource_count"],
            "reviewed_version_count": graph["reviewed_version_count"],
            "state": "catalogued_not_verified",
        }
    else:
        result = store.export()
    serialized = canonical(result)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("xb") as output:
            output.write((serialized + "\n").encode("utf-8"))
    print(serialized)
    return result


if __name__ == "__main__":
    main()
