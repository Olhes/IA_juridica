"""Immutable, content-addressed conversion evidence; not legal source verification."""

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceEvidence:
    schema_version: int
    evidence_id: str
    pdf_sha256: str
    markdown_sha256: str
    pdf_size_bytes: int
    markdown_size_bytes: int
    provenance_state: str


def persist_source_evidence(
    pdf_path: Path, markdown_path: Path, markdown: str, store_dir: Path
) -> SourceEvidence:
    """Publish only after the existing Markdown write; reject divergent retries."""
    pdf_digest = hashlib.sha256()
    pdf_size = 0
    with pdf_path.open("rb") as pdf:
        while chunk := pdf.read(1024 * 1024):
            pdf_digest.update(chunk)
            pdf_size += len(chunk)
    markdown_bytes = markdown_path.read_bytes()
    if markdown_bytes != markdown.encode("utf-8"):
        raise ValueError("Persisted Markdown does not match converted content")

    pdf_hash = pdf_digest.hexdigest()
    evidence = SourceEvidence(
        schema_version=1,
        evidence_id=f"pdf-sha256-{pdf_hash}",
        pdf_sha256=pdf_hash,
        markdown_sha256=hashlib.sha256(markdown_bytes).hexdigest(),
        pdf_size_bytes=pdf_size,
        markdown_size_bytes=len(markdown_bytes),
        provenance_state="unverified",
    )
    store_dir.mkdir(parents=True, exist_ok=True)
    destination = store_dir / f"{evidence.evidence_id}.json"
    payload = (json.dumps(asdict(evidence), sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")

    # Un archivo temporal duradero en el mismo directorio y un enlace físico exclusivo
    # impiden que escritores concurrentes reemplacen un registro existente (incluso al reiniciar).
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=store_dir, prefix=".evidence-", delete=False) as temp:
            temp_path = Path(temp.name)
            temp.write(payload)
            temp.flush()
            os.fsync(temp.fileno())
        try:
            os.link(temp_path, destination)
        except FileExistsError:
            if destination.read_bytes() != payload:
                raise ValueError(f"Evidence collision or tampered record: {evidence.evidence_id}")
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return evidence
