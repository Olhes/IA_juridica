"""Regla de solapamiento que mapea fragmentos recuperados a segmentos del gold.

Regla documentada (``legal_qa`` y ``retrieval``): sea ``S(x)`` el conjunto de
n-gramas de ``SHINGLE`` caracteres de ``compact(x)``. Un fragmento ``c``
corresponde a un segmento ``s`` si

* ``|S(c) ∩ S(s)| / |S(s)| >= SEGMENT_COVERAGE``  (el fragmento contiene la mayor
  parte del segmento), **o**
* ``|S(c) ∩ S(s)| / |S(c)| >= CHUNK_COVERAGE``  (el fragmento es, casi por completo,
  una parte del segmento).

Un fragmento puede corresponder a varios segmentos (uno largo cubre varios) y
varios fragmentos a un mismo segmento. Los fragmentos sin correspondencia se
conservan como ``unmapped:<huella>``: cuentan como devueltos pero no relevantes.
Limitación: texto idéntico repetido en dos documentos corresponde a ambos segmentos.
"""

import hashlib
from collections import defaultdict
from dataclasses import dataclass

from utils.text_match import compact

SHINGLE = 10
SEGMENT_COVERAGE = 0.6
CHUNK_COVERAGE = 0.6


def shingles(text: str, n: int = SHINGLE) -> set:
    flat = compact(text)
    return {flat[i : i + n] for i in range(len(flat) - n + 1)} if len(flat) >= n else set()


def unmapped_id(text: str) -> str:
    return "unmapped:" + hashlib.sha256(compact(text).encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class Match:
    segment_id: str
    segment_coverage: float
    chunk_coverage: float


class SegmentMatcher:
    def __init__(self, corpus, *, segment_coverage=SEGMENT_COVERAGE, chunk_coverage=CHUNK_COVERAGE):
        self.segment_coverage, self.chunk_coverage = segment_coverage, chunk_coverage
        self.sizes: dict = {}
        self._index: dict = defaultdict(list)
        for segment in corpus.segments.values():
            grams = shingles(segment.text)
            self.sizes[segment.id] = len(grams)
            for gram in grams:
                self._index[gram].append(segment.id)

    def matches(self, text: str) -> list:
        grams = shingles(text)
        if not grams:
            return []
        counts: dict = defaultdict(int)
        for gram in grams:
            for segment_id in self._index.get(gram, ()):
                counts[segment_id] += 1
        found = []
        for segment_id, shared in counts.items():
            seg_cov, chunk_cov = shared / self.sizes[segment_id], shared / len(grams)
            if seg_cov >= self.segment_coverage or chunk_cov >= self.chunk_coverage:
                found.append(Match(segment_id, seg_cov, chunk_cov))
        return sorted(found, key=lambda m: m.segment_id)

    def ids(self, text: str) -> list:
        """IDs de segmentos del fragmento, o ``[unmapped:<huella>]`` si no corresponde a ninguno."""
        found = [m.segment_id for m in self.matches(text)]
        return found or [unmapped_id(text)]
