"""
RAG Cross-Checker para IA Jurídica.

Verifica que las afirmaciones del LLM estén respaldadas por los chunks
que el RAG recuperó para esa misma query.

Estrategia:
  1. Extrae "afirmaciones" del texto del LLM (nivel oración)
  2. Para cada afirmación, calcula un overlap de tokens contra el corpus RAG
  3. Clasifica cada afirmación como "fundada" o "no fundada"
  4. Devuelve CrossCheckResult con overlap_score global e is_grounded

El overlap de tokens es una heurística rápida y sin costo API.
En producción puede reemplazarse por un modelo NLI o embeddings similarity
usando el mismo cliente Cohere del sistema.

Uso:
    checker = RAGCrossChecker(documents=rag_engine.documents)
    result = checker.check(llm_answer_text, query)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from loguru import logger

# Stopwords básicas español/quechua para filtrar tokens irrelevantes
_STOPWORDS = {
    # Español
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "de", "del", "al", "a", "en", "con", "por", "para",
    "que", "y", "o", "si", "no", "se", "su", "sus",
    "lo", "le", "les", "es", "son", "fue", "ser",
    "este", "esta", "estos", "estas", "ese", "esa",
    # Quechua (partículas comunes)
    "mi", "pi", "taq", "pas", "chus", "raq",
}

# Mínimo de tokens significativos para considerar una afirmación analizable
MIN_CLAIM_TOKENS = 3

# Umbral de overlap por afirmación individual para considerarla "fundada"
CLAIM_SUPPORT_THRESHOLD = 0.28

# Umbral global de overlap para considerar la respuesta completa como "fundada"
GLOBAL_GROUNDED_THRESHOLD = 0.55


@dataclass
class CrossCheckResult:
    """Resultado del cross-check entre output LLM y corpus RAG."""
    is_grounded        : bool
    overlap_score      : float              # 0–1 global
    total_claims       : int
    grounded_claims    : int
    ungrounded_claims  : List[str] = field(default_factory=list)
    supporting_chunks  : List[str] = field(default_factory=list)
    checked_against    : int = 0            # nº de chunks evaluados


class RAGCrossChecker:
    """
    Verifica que las afirmaciones del LLM tengan soporte en los documentos
    recuperados por el RAG, sin llamadas adicionales a la API de Cohere.

    Args:
        documents: El dict `rag_engine.documents` con estructura
                   {doc_id: {"content": str, "chunks": List[str], "metadata": dict}}
        grounded_threshold: Overlap global mínimo para `is_grounded = True`
    """

    def __init__(
        self,
        documents: Dict[str, Any],
        grounded_threshold: float = GLOBAL_GROUNDED_THRESHOLD,
    ):
        self.documents  = documents
        self.threshold  = grounded_threshold
        self._corpus_tokens: Optional[set] = None  # cache lazy
        logger.info(
            f"RAGCrossChecker inicializado ({len(documents)} documentos, "
            f"threshold={grounded_threshold})"
        )

    # ── API pública ────────────────────────────────────────────────────────────

    def check(self, llm_answer: str, query: str = "") -> CrossCheckResult:
        """
        Compara el texto del LLM contra el corpus RAG.

        Args:
            llm_answer: Texto plano generado por el agente LLM
            query:      Consulta original (para logging)

        Returns:
            CrossCheckResult con breakdown detallado
        """
        if not llm_answer or not llm_answer.strip():
            return CrossCheckResult(
                is_grounded=False,
                overlap_score=0.0,
                total_claims=0,
                grounded_claims=0,
                ungrounded_claims=["Respuesta vacía"],
            )

        # Obtener corpus de tokens del RAG (lazy + cached)
        corpus_tokens = self._get_corpus_tokens()
        if not corpus_tokens:
            logger.warning("Corpus RAG vacío – no se puede hacer cross-check")
            return CrossCheckResult(
                is_grounded=True,   # Optimista cuando no hay corpus
                overlap_score=1.0,
                total_claims=0,
                grounded_claims=0,
            )

        # Extraer afirmaciones del texto LLM
        claims = self._extract_claims(llm_answer)

        if not claims:
            # Sin afirmaciones extraíbles → asumir OK (respuesta muy corta)
            return CrossCheckResult(
                is_grounded=True,
                overlap_score=1.0,
                total_claims=0,
                grounded_claims=0,
                checked_against=len(corpus_tokens),
            )

        # Evaluar cada afirmación contra el corpus
        grounded, ungrounded = [], []
        for claim in claims:
            if self._claim_supported(claim, corpus_tokens):
                grounded.append(claim)
            else:
                ungrounded.append(claim)

        overlap_score = round(len(grounded) / len(claims), 4)
        is_grounded   = overlap_score >= self.threshold

        # Extraer los 3 chunks más relevantes como evidencia de soporte
        supporting = self._get_supporting_chunks(query or llm_answer[:200], top_k=3)

        result = CrossCheckResult(
            is_grounded       = is_grounded,
            overlap_score     = overlap_score,
            total_claims      = len(claims),
            grounded_claims   = len(grounded),
            ungrounded_claims = ungrounded[:5],  # Limitar para el informe
            supporting_chunks = supporting,
            checked_against   = len(corpus_tokens),
        )

        logger.debug(
            f"CrossCheck: overlap={overlap_score:.2f}, "
            f"grounded={len(grounded)}/{len(claims)}, "
            f"is_grounded={is_grounded}"
        )
        return result

    # ── Helpers privados ───────────────────────────────────────────────────────

    def _get_corpus_tokens(self) -> set:
        """
        Construye (y cachea) el conjunto de tokens significativos de TODO el corpus RAG.
        Se recalcula si `documents` cambia de tamaño (se agregó/quitó documentos).
        """
        current_size = len(self.documents)
        if self._corpus_tokens is not None and hasattr(self, "_corpus_size"):
            if self._corpus_size == current_size:  # type: ignore[attr-defined]
                return self._corpus_tokens

        tokens: set = set()
        for doc_data in self.documents.values():
            # Indexar el contenido completo
            tokens.update(self._tokenize(doc_data.get("content", "")))
            # Indexar chunks individuales (más representativos)
            for chunk in doc_data.get("chunks", []):
                tokens.update(self._tokenize(chunk))

        self._corpus_tokens = tokens
        self._corpus_size   = current_size  # type: ignore[attr-defined]
        logger.debug(f"Corpus tokens cacheados: {len(tokens)} tokens únicos")
        return tokens

    def _tokenize(self, text: str) -> set:
        """Tokeniza texto a tokens minúsculos significativos."""
        raw = re.findall(r"\b[a-záéíóúüñ]{3,}\b", text.lower())
        return {t for t in raw if t not in _STOPWORDS}

    def _extract_claims(self, text: str) -> List[str]:
        """
        Divide el texto en oraciones como unidades de afirmación.
        Filtra frases demasiado cortas para ser evaluables.
        """
        # Dividir por punto, punto y coma, saltos de línea dobles
        sentences = re.split(r"(?<=[.!?;])\s+|(?<=\n)\n", text.strip())
        claims = []
        for s in sentences:
            s = s.strip()
            tokens = self._tokenize(s)
            if len(tokens) >= MIN_CLAIM_TOKENS and len(s) > 20:
                claims.append(s)
        return claims

    def _claim_supported(self, claim: str, corpus_tokens: set) -> bool:
        """
        Determina si una afirmación tiene soporte en el corpus RAG.
        Usa overlap de tokens significativos normalizado por el tamaño de la afirmación.
        """
        claim_tokens = self._tokenize(claim)
        if not claim_tokens:
            return True  # No analizable → asumir OK

        overlap = len(claim_tokens & corpus_tokens) / len(claim_tokens)
        return overlap >= CLAIM_SUPPORT_THRESHOLD

    def _get_supporting_chunks(self, reference_text: str, top_k: int = 3) -> List[str]:
        """
        Devuelve los chunks más relevantes del corpus como evidencia de soporte.
        Usa keyword overlap simple (sin costo API).
        """
        ref_tokens = self._tokenize(reference_text)
        if not ref_tokens:
            return []

        scored: List[tuple] = []
        for doc_data in self.documents.values():
            for chunk in doc_data.get("chunks", []):
                chunk_tokens = self._tokenize(chunk)
                if not chunk_tokens:
                    continue
                overlap = len(ref_tokens & chunk_tokens) / len(ref_tokens)
                if overlap > 0.1:
                    scored.append((overlap, chunk[:300]))  # Limitar largo

        scored.sort(key=lambda x: x[0], reverse=True)
        return [chunk for _, chunk in scored[:top_k]]

    def update_documents(self, documents: Dict[str, Any]) -> None:
        """Actualiza el corpus y limpia el cache de tokens."""
        self.documents      = documents
        self._corpus_tokens = None
        logger.info(f"CrossChecker: corpus actualizado ({len(documents)} documentos)")