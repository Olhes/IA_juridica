"""Package the reviewed beta corpus (SQLite and its nine hash-checked PDFs)."""
import argparse
from contextlib import closing
from hashlib import file_digest, sha256
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "backend" / "docs"


def package(database: Path, output: Path):
    with TemporaryDirectory() as temporary:
        snapshot = Path(temporary) / "sat_graph.sqlite3"
        with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(snapshot)) as copy:
                source.backup(copy)
                rows = copy.execute(
                    "SELECT payload FROM sat_nodes WHERE kind='DocumentaryRevision' "
                    "AND json_extract(payload, '$.editorial_superseded_by') IS NULL"
                ).fetchall()
                if len(rows) != 9 or copy.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise ValueError("Expected nine published beta sources and a valid database")

        files = []
        for (payload,) in rows:
            revision = json.loads(payload)
            if sha256(revision["markdown"].encode()).hexdigest() != revision["markdown_sha256"]:
                raise ValueError("Published Markdown hash mismatch")
            directory = revision.get("directory")
            candidate = revision.get("candidate_pdf")
            if directory and Path(directory).name == directory:
                relative = Path("backend/docs/sat_reviews") / directory / "source.pdf"
                pdf = ROOT / relative
            elif candidate and Path(candidate).name == candidate:
                relative = Path("backend/docs/sat_reviews/published-references") / candidate
                pdf = ROOT / relative
                if not pdf.is_file():
                    pdf = ROOT / "temp" / "sat-corpus-work" / "pdf" / candidate
            else:
                raise ValueError("Missing source PDF locator")
            with pdf.open("rb") as stream:
                if "pdf-sha256-" + file_digest(stream, "sha256").hexdigest() != revision["evidence_id"]:
                    raise ValueError(f"PDF hash mismatch: {pdf.name}")
            files.append((pdf, relative))
        if len({relative for _, relative in files}) != 9:
            raise ValueError("Duplicate published sources")
        with ZipFile(output, "x", compression=ZIP_DEFLATED) as bundle:
            bundle.write(snapshot, "backend/docs/sat_graph.sqlite3")
            for pdf, relative in files:
                bundle.write(pdf, relative.as_posix())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--db", type=Path, default=DOCS / "sat_graph.sqlite3")
    args = parser.parse_args()
    package(args.db, args.output)
