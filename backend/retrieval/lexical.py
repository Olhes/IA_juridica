"""BM25S compartido por SAT y la recuperación léxica local de LightRAG."""

import re
import unicodedata

from bm25s import BM25

# Spanish function words and high-frequency conversational fillers that skew BM25
# toward short unrelated articles when left unfiltered.
SPANISH_STOPWORDS: frozenset[str] = frozenset({
    "a", "al", "algo", "ante", "asi", "aunque", "bien", "como", "con", "contra",
    "cual", "cuales", "cuando", "de", "del", "desde", "donde", "e", "el", "ella",
    "ellas", "ello", "ellos", "en", "entre", "era", "es", "esa", "esas", "ese",
    "eso", "esos", "esta", "estas", "este", "esto", "estos", "fue", "ha", "haber",
    "hace", "hacer", "hacerlo", "hacerla", "hacia", "hasta", "hay", "la", "las",
    "le", "les", "lo", "los", "mas", "me", "mi", "mis", "muy", "ni", "no", "nos",
    "o", "os", "para", "pero", "por", "porque", "puedo", "puede", "pueden", "que",
    "quien", "quienes", "se", "sea", "segun", "ser", "si", "sin", "sobre", "son",
    "su", "sus", "tambien", "te", "tener", "tiene", "tienen", "todo", "todos",
    "tu", "tus", "un", "una", "unas", "uno", "unos", "y", "ya",
})

_ES_SUFFIXES: tuple[tuple[str, str, int], ...] = (
    # Longest derivational/inflectional endings first; third element is minimum stem length.
    ("imientos", "", 4),
    ("amientos", "", 4),
    ("imiento", "", 4),
    ("amiento", "", 4),
    ("aciones", "", 4),
    ("iciones", "", 4),
    ("adores", "", 4),
    ("adoras", "", 4),
    ("acion", "", 4),
    ("icion", "", 4),
    ("mente", "", 4),
    ("istas", "", 4),
    ("arios", "", 4),
    ("arias", "", 4),
    ("icios", "", 4),
    ("icias", "", 4),
    ("ador", "", 4),
    ("adora", "", 4),
    ("ando", "", 4),
    ("iendo", "", 4),
    ("ista", "", 4),
    ("ario", "", 4),
    ("aria", "", 4),
    ("icio", "", 4),
    ("icia", "", 4),
    ("ces", "z", 3),
    ("es", "", 4),
    ("ar", "", 4),
    ("er", "", 4),
    ("ir", "", 4),
    ("as", "", 3),
    ("os", "", 3),
    ("a", "", 3),
    ("o", "", 3),
    ("e", "", 4),
    ("s", "", 3),
)


def terms(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", normalized)


def _stem_es(token: str) -> str:
    if len(token) <= 3 or any(ch.isdigit() for ch in token):
        return token
    for suffix, replacement, min_stem in _ES_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= min_stem:
            return token[: -len(suffix)] + replacement
    return token


def legal_terms(text: str) -> list[str]:
    """Spanish legal tokenizer: removes stopwords and applies light stemming."""
    raw = terms(text)
    if not raw:
        return []
    filtered = [token for token in raw if token not in SPANISH_STOPWORDS]
    selected = filtered or raw
    return [_stem_es(token) for token in selected]


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
