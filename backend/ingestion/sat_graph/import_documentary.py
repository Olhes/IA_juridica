"""Import human-approved documentary structures without inventing legal dates.

Run from backend: python -m ingestion.sat_graph.import_documentary
The resulting DocumentaryComponent nodes are not legally reviewed CTVs.
"""
import argparse
import hashlib
import json
from pathlib import Path

from ingestion.sat_graph.store import SATGraphStore, canonical, digest
from ingestion.source_evidence import SourceEvidence
from dataclasses import asdict


def sha(data):
    return hashlib.sha256(data).hexdigest()


def prepare(directory):
    review = json.loads((directory / "structure-review.json").read_text(encoding="utf-8"))
    if review.get("review_state") not in {"user_approved_view", "user_approved_structure"}:
        raise ValueError("La estructura no consta como aprobada por el usuario")
    raw = (directory / "source.md").read_bytes()
    pdf = (directory / "source.pdf").read_bytes()
    for filename, data in (("source.md", raw), ("source.pdf", pdf)):
        hashes = review.get("source_sha256") or {k: v["sha256"] for k, v in review["source_files"].items()}
        if sha(data) != hashes[filename]:
            raise ValueError(f"Hash incorrecto: {filename}")
    original = raw.decode("utf-8")
    corrected_path = directory / "source.corrected.md"
    changes = []
    corrected = original
    if corrected_path.exists():
        correction = json.loads((directory / "text-corrections.json").read_text(encoding="utf-8"))
        corrected = corrected_path.read_bytes().decode("utf-8")
        if sha(raw) != correction["original_sha256"] or sha(corrected.encode()) != correction["corrected_sha256"]:
            raise ValueError("Hash de correcciones incorrecto")
        for c in correction["changes"]:
            start = c.get("original_start", c.get("start"))
            end = c.get("original_end", c.get("end"))
            if original[start:end] != c["original"]:
                raise ValueError("La corrección no corresponde al texto original")
            changes.append((start, end, c["replacement"]))
        changes.sort()
        pos = 0
        parts = []
        for start, end, replacement in changes:
            if start < pos or end <= start:
                raise ValueError("Correcciones solapadas")
            parts.extend((original[pos:start], replacement))
            pos = end
        if "".join(parts) + original[pos:] != corrected:
            raise ValueError("El Markdown corregido no coincide con las correcciones")

    def translate(pos):
        delta = 0
        for start, end, replacement in changes:
            if start < pos < end:
                raise ValueError(f"Límite estructural dentro de una corrección: {pos}")
            if pos >= end:
                delta += len(replacement) - (end - start)
        return pos + delta

    nodes = review["nodes"]
    by_id = {n["id"]: n for n in nodes}
    if len(by_id) != len(nodes):
        raise ValueError("Identificadores de estructura duplicados")
    for node in nodes:
        start, end = node["start"], node["end"]
        if not (0 <= start < end <= len(original)) or sha(original[start:end].encode()) != node["source_span_sha256"]:
            raise ValueError(f"Fragmento inválido: {node['id']}")
        parent = node.get("parent_id")
        if parent and (parent not in by_id or not (by_id[parent]["start"] <= start < end <= by_id[parent]["end"])):
            raise ValueError(f"Jerarquía inválida: {node['id']}")
        translate(start); translate(end)
    return review, pdf, raw, corrected, changes, translate


def import_one(store, directory):
    review, pdf, raw, corrected, changes, translate = prepare(directory)
    pdf_hash, original_hash = sha(pdf), sha(raw)
    evidence_id = f"pdf-sha256-{pdf_hash}"
    if review.get("evidence_id", evidence_id) != evidence_id:
        raise ValueError("Identidad PDF no coincide con revisión")
    evidence = SourceEvidence(1, evidence_id, pdf_hash, original_hash, len(pdf), len(raw), "unverified")
    review_hash = sha((directory / "structure-review.json").read_bytes())
    revision_id = "documentary-revision:" + digest(canonical([evidence_id, review_hash, sha(corrected.encode())]))
    node_ids = {n["id"]: "documentary-component:" + digest(canonical([revision_id, n["id"]])) for n in review["nodes"]}
    audit = {"review_hash": review_hash, "provenance_state": "user_approved_documentary", "legal_validity": "assumed_current_not_verified"}
    with store._transaction() as db:
        for (payload,) in db.execute("SELECT payload FROM sat_nodes WHERE kind='DocumentaryRevision'"):
            prior = json.loads(payload)
            if prior.get('evidence_id') == evidence_id and prior.get('previous_revision'):
                raise ValueError('Esta fuente ya fue corregida en el editor SAT; exporte la edición actual, no reimporte el artefacto anterior')
        store._node(db, evidence_id, "Source", asdict(evidence))
        existing = db.execute("SELECT markdown FROM sat_documents WHERE evidence_id=?", (evidence_id,)).fetchone()
        if existing and existing[0] != raw.decode("utf-8"):
            raise ValueError("La fuente almacenada difiere del Markdown original")
        db.execute("INSERT OR IGNORE INTO sat_documents VALUES (?,?,'pending_review')", (evidence_id, raw.decode("utf-8")))
        store._node(db, revision_id, "DocumentaryRevision", {**audit, "evidence_id": evidence_id, "directory": directory.name, "review_state": review["review_state"], "text_review_state": review.get("text_review_state"), "markdown": corrected, "markdown_sha256": sha(corrected.encode()), "original_markdown_sha256": original_hash, "correction_count": len(changes)})
        store._edge(db, revision_id, "evidenced_by", evidence_id, audit)
        for n in review["nodes"]:
            start, end = translate(n["start"]), translate(n["end"])
            identity = node_ids[n["id"]]
            store._node(db, identity, "DocumentaryComponent", {**audit, "revision_id": revision_id, "source_node_id": n["id"], "kind": n["kind"], "label": n["label"], "start": start, "end": end, "text_sha256": sha(corrected[start:end].encode())})
            store._edge(db, identity, "part_of_revision", revision_id, audit)
            if n.get("parent_id"):
                store._edge(db, node_ids[n["parent_id"]], "documentary_has_part", identity, audit)
        store._reject_cycles(db, "documentary_has_part")
    return {"document": directory.name, "components": len(node_ids), "corrections": len(changes), "revision_id": revision_id, "text_review_state": review.get("text_review_state")}


def main():
    root = Path(__file__).resolve().parents[2] / "docs"
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=root / "sat_graph.sqlite3")
    parser.add_argument("--reviews", type=Path, default=root / "sat_reviews")
    args = parser.parse_args()
    store = SATGraphStore(args.db)
    results, errors = [], []
    for directory in sorted(args.reviews.iterdir()):
        if not (directory / "structure-review.json").exists():
            continue
        try:
            results.append(import_one(store, directory))
        except Exception as exc:
            errors.append({"document": directory.name, "error": str(exc)})
    print(json.dumps({"imported": results, "errors": errors}, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
