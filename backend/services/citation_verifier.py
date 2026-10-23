"""Extracción y verificación determinista de citas legales (Ley, artículo, Casación, D.S.).

No juzga si la norma citada es vigente ni si dice lo que el texto afirma: solo
comprueba que la cita aparece en la evidencia recuperada. Una cita ``verified``
es *trazable* a un extracto; una ``unverified`` no se encontró y puede ser una
invención. El texto del extracto proviene del corpus, nunca del modelo.
"""

import re
from dataclasses import dataclass
from typing import Optional

from utils.text_match import compact, fold, spaced_ocr_ratio

# Códigos reconocidos tras un número de artículo: clave -> patrón sobre texto normalizado.
_CODES = (
    ("cna", r"codigo de los ninos|\bcna\b"),
    ("cpc", r"codigo procesal civil|\bcpc\b"),
    ("cpp", r"codigo procesal penal|\bcpp\b"),
    ("cc", r"codigo civil|\bcc\b"),
    ("cp", r"codigo penal|\bcp\b"),
    ("const", r"constitucion"),
)
_LEY = re.compile(r"ley\s+(?:n[\s.°º]*0?\s*)?(\d{4,6})\b")
_ARTICLE = re.compile(
    r"art(?:iculos?|s?)?[.;]?\s*"
    r"(\d{1,4}(?:-[a-z])?(?:\s*(?:,|y|e)\s*\d{1,4}(?:-[a-z])?)*)"
)
_CASACION = re.compile(r"casacion\s+(?:n[\s.°º]*0?\s*)?(\d{1,5})\s*-\s*(\d{4})")
_DS = re.compile(r"decreto supremo\s+(?:n[\s.°º]*0?\s*)?(\d{3})\s*-\s*(\d{4})\s*-\s*([a-z]+)")
_WINDOW = 70


@dataclass(frozen=True)
class Citation:
    kind: str  # ley | articulo | casacion | decreto_supremo
    key: str
    raw: str


def despace(text: str) -> str:
    """Une las rachas de letras sueltas del OCR espaciado (``l a v i d a`` -> ``lavida``)."""
    return re.sub(r"(?<=\b\w) (?=\w\b)", "", re.sub(r"(?<=\b\w) (?=\w\b)", "", text))


_LEADING = re.compile(
    r"^[\s,.;:()\-]*(?:(?:inc(?:iso)?|lit(?:eral)?|num(?:eral)?)\.?\s*[a-z0-9]+[\s,.;:()\-]*)*"
    r"(?:(?:de la|de los|de las|del|de)\s+)?"
)


def _code_after(folded: str, end: int) -> Optional[str]:
    """Código o ley que acompaña inmediatamente al artículo (no los de más adelante)."""
    tail = folded[end : end + _WINDOW]
    tail = tail[_LEADING.match(tail).end() :]
    ley = re.match(r"ley\s+(?:n[\s.°º]*0?\s*)?(\d{4,6})", tail)
    if ley:
        return f"ley{ley.group(1)}"
    for code, pattern in _CODES:
        if re.match(pattern.replace("\b", ""), tail):
            return code
    return None


def extract_citations(text: str) -> list:
    """Citas únicas (por clave) en orden de aparición."""
    norm = fold(text)
    found: dict = {}

    def add(position, kind, key, raw_span):
        raw = text[raw_span[0] : raw_span[1]].strip()
        found.setdefault(key, (position, Citation(kind, key, raw)))

    for m in _CASACION.finditer(norm):
        add(m.start(), "casacion", f"casacion:{int(m.group(1))}-{m.group(2)}", m.span())
    for m in _DS.finditer(norm):
        add(m.start(), "decreto_supremo", f"ds:{m.group(1)}-{m.group(2)}-{m.group(3)}", m.span())
    for m in _LEY.finditer(norm):
        add(m.start(), "ley", f"ley:{m.group(1)}", m.span())
    for m in _ARTICLE.finditer(norm):
        code = _code_after(norm, m.end())
        for number in re.findall(r"\d{1,4}(?:-[a-z])?", m.group(1)):
            key = f"{code}:art:{number}" if code else f"art:{number}"
            add(m.start(), "articulo", key, m.span())
    return [citation for _, citation in sorted(found.values(), key=lambda item: item[0])]


def _article_parts(key: str):
    """``("cc", "475")`` para ``cc:art:475``; ``("", "475")`` para ``art:475``; ``None`` si no es artículo."""
    match = re.fullmatch(r"(?:(.+?):)?art:(.+)", key)
    return (match.group(1) or "", match.group(2)) if match else None


def citation_matches(cited: str, reference: str) -> bool:
    """Igualdad de claves; un artículo sin código identificado coincide por número."""
    if cited == reference:
        return True
    a, b = _article_parts(cited), _article_parts(reference)
    return bool(a and b and a[1] == b[1] and (not a[0] or not b[0]))


def evidence_keys(text: str) -> set:
    keys = {c.key for c in extract_citations(text)}
    if spaced_ocr_ratio(text) > 0.5:
        keys |= {c.key for c in extract_citations(despace(text))}
    return keys


def _excerpt(text: str, citation: Citation, width: int = 160) -> Optional[str]:
    number = re.search(r"\d[\d-]*\d|\d", citation.key.rsplit(":", 1)[-1])
    if not number:
        return None
    flat = re.sub(r"\s+", " ", text)
    for match in re.finditer(re.escape(number.group(0)).replace(r"\-", r"\s*-\s*"), flat):
        start = max(0, match.start() - width // 2)
        return flat[start : start + width].strip()
    return None


def verify_citations(answer_text: str, evidence: list) -> list:
    """Verifica cada cita de ``answer_text`` contra ``evidence`` (``[{source, text}]``).

    Devuelve ``[{key, text, status, source, excerpt}]`` con ``status`` en
    ``verified`` | ``unverified``. ``text`` es lo que citó la respuesta.
    """
    results = []
    prepared = [
        (item.get("source"), item.get("text") or "", evidence_keys(item.get("text") or ""))
        for item in evidence
    ]
    for citation in extract_citations(answer_text):
        hit = next(
            (
                (source, text)
                for source, text, keys in prepared
                if any(citation_matches(citation.key, key) for key in keys)
                or (
                    citation.kind in {"ley", "casacion", "decreto_supremo"}
                    and compact(citation.key.split(":", 1)[1]) in compact(text)
                )
            ),
            None,
        )
        results.append(
            {
                "key": citation.key,
                "text": citation.raw,
                "status": "verified" if hit else "unverified",
                "source": hit[0] if hit else None,
                "excerpt": _excerpt(hit[1], citation) if hit else None,
            }
        )
    return results
