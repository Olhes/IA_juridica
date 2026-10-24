"""Segmentación determinista del corpus Markdown en segmentos citables.

Un *segmento* es un bloque de Markdown separado por líneas en blanco, tras
descartar ruido de página (imágenes, URLs, contadores ``3/17``, sellos de
fecha). Su identificador es ``<doc_id>#<ordinal>`` (ordinal desde 1) y su huella
``sha`` (12 hex de ``compact``) detecta que el texto cambió. Cambiar las reglas
exige subir ``SEGMENTER_VERSION`` y regenerar el gold.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from utils.text_match import compact, spaced_ocr_ratio, strip_accents

SEGMENTER_VERSION = 1
MIN_COMPACT_CHARS = 10
DEFAULT_CORPUS_DIR = Path(__file__).resolve().parents[2] / "docs" / "processed"

_NOISE = (
    re.compile(r"^<!--.*-->$"),
    re.compile(r"^https?://\S+$"),
    re.compile(r"^\d+\s*/\s*\d+$"),
    re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4},\s*\d{1,2}:\d{2}\s*[ap]\.?\s*m\.?$", re.I),
    re.compile(r"^notebooklm$", re.I),
)


@dataclass(frozen=True)
class Segment:
    id: str
    doc_id: str
    ordinal: int
    text: str
    sha: str


@dataclass(frozen=True)
class Document:
    doc_id: str
    path: Path
    segments: tuple
    spaced_ocr_ratio: float


def doc_id_for(path) -> str:
    stem = strip_accents(Path(path).stem).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")[:48].strip("-")
    return slug or "doc"


def _is_noise(line: str) -> bool:
    return any(pattern.match(line.strip()) for pattern in _NOISE)


def segment_text(doc_id: str, text: str) -> tuple:
    segments, ordinal = [], 0
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        lines = [ln for ln in block.split("\n") if ln.strip() and not _is_noise(ln)]
        body = re.sub(r"\s+", " ", " ".join(lines)).strip()
        if len(compact(body)) < MIN_COMPACT_CHARS:
            continue
        ordinal += 1
        sha = hashlib.sha256(compact(body).encode("utf-8")).hexdigest()[:12]
        segments.append(Segment(f"{doc_id}#{ordinal}", doc_id, ordinal, body, sha))
    return tuple(segments)


def load_document(path) -> Document:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    doc_id = doc_id_for(path)
    return Document(doc_id, path, segment_text(doc_id, text), spaced_ocr_ratio(text))


class Corpus:
    """Documentos y segmentos del corpus procesado, indexados por id."""

    def __init__(self, documents):
        documents = list(documents)
        self.documents = {d.doc_id: d for d in documents}
        self.segments = {s.id: s for d in documents for s in d.segments}
        if len(self.documents) != len(list(documents)):
            raise ValueError("Dos documentos del corpus producen el mismo doc_id")

    @classmethod
    def load(cls, directory=DEFAULT_CORPUS_DIR):
        paths = sorted(Path(directory).glob("*.md"))
        return cls([load_document(p) for p in paths])

    def revision(self) -> str:
        """Huella del contenido segmentado; cambia si cambia cualquier segmento."""
        digest = hashlib.sha256(f"segmenter-v{SEGMENTER_VERSION}".encode())
        for segment_id in sorted(self.segments):
            digest.update(f"{segment_id}:{self.segments[segment_id].sha}".encode())
        return digest.hexdigest()[:16]

    def full_text(self, doc_id: str) -> str:
        return " ".join(s.text for s in self.documents[doc_id].segments)

    def all_text(self) -> str:
        return " ".join(s.text for s in self.segments.values())
