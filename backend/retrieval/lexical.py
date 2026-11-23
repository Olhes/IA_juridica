"""BM25S compartido por SAT y la recuperación léxica local de LightRAG."""

import re
import unicodedata

from bm25s import BM25


def terms(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", normalized)


class BM25Index:
    """Adapta las filas de BM25S a identificadores sin imponer el desempate."""

    def __init__(self, texts: dict[str, str], *, tokenize=terms, k1=1.2, average_floor=0.0):
        self._ids = tuple(texts)
        self._tokenize = tokenize
        self._index: BM25 | None = None
        self._scale = 1.0
        tokenized = [tokenize(text) for text in texts.values()]
        if not any(tokenized):
            return
        b = 0.75
        if average_floor:
            mean = sum(map(len, tokenized)) / len(tokenized)
            if mean < average_floor:
                # Reparametrize BM25S for LightRAG's historical max(mean, 1)
                # denominator. Its term-frequency numerator is rescaled below.
                ratio = mean / average_floor
                factor = 1 - b + b * ratio
                self._scale = (k1 + 1) / (k1 * factor + 1)
                k1, b = k1 * factor, b * ratio / factor
        # Match the historical formulas: ATIRE term frequency and Lucene IDF.
        self._index = BM25(method="atire", idf_method="lucene", k1=k1, b=b, dtype="float64")
        self._index.index(tokenized, show_progress=False)

    def score(self, query: str) -> dict[str, float]:
        query_terms = sorted(set(self._tokenize(query)))
        if self._index is None or not query_terms:
            return {}
        scores = self._index.get_scores(query_terms)
        return {self._ids[i]: float(scores[i]) * self._scale for i in scores.nonzero()[0]}
