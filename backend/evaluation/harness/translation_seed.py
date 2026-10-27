"""Semilla del gold de traducción: pares *candidatos* extraídos de textos impresos.

Fuentes (en ``backend/docs/processed_backup``, no indexadas):

* Manual para el empleo del quechua **cusco-collao** en la administración de justicia.
* Manual para el empleo del quechua **chanka** en la administración de justicia.
* Ley 30364, edición quechua-castellano (Biblioteca del Congreso, 2025): pares por artículo.
  La variante exacta no consta en el archivo: se marca ``sureno-sin-confirmar``.

Cada par conserva su origen; ``reference_quality`` es ``clean`` solo si la fila no mezcla
alternativas ni oraciones (las dudosas se descartan de la semilla y se cuentan). Nada de
esto es una verdad lingüística: todos los pares son ``candidate`` y esperan a dos hablantes
nativos. Regenerar: ``uv run python -m evaluation.harness.translation_seed`` (desde ``backend/``).
"""

import hashlib
import re
from collections import Counter
from pathlib import Path

from evaluation.harness.translation_gold import (
    SOURCES_DIR,
    TRANSLATION_PATH,
    TranslationPair,
    dump_pairs,
    strip_page_noise,
    verify_pair,
)
from services.translation_qe import SPANISH_STOPWORDS, detect_language, tokens
from utils.text_match import fold

CUSCO = "Manual quechua cusco collao administracion de justicia.md"
CHANKA = "manual quechua chanka en la administracion de justicia.md"
LEY = "Ley 30364 quechua-castellano prevencion de la violencia contra la mujer e intrafamiliar.md"

# (archivo, variante, primera línea, última línea, etiqueta); intervalos de 1 en adelante.
SENTENCE_SECTIONS = (
    (CUSCO, "cusco-collao", 1131, 1186, "demanda de alimentos"),
    (CUSCO, "cusco-collao", 1386, 1633, "violencia contra la mujer"),
    (CHANKA, "chanka", 1215, 1254, "alimentos"),
    (CHANKA, "chanka", 1459, 1760, "violencia contra la mujer"),
)
TERM_SECTIONS = (
    (CUSCO, "cusco-collao", 916, 1050),
    (CUSCO, "cusco-collao", 2463, 2481),
    (CUSCO, "cusco-collao", 2482, 2850),
    (CHANKA, "chanka", 930, 1110),
    (CHANKA, "chanka", 1255, 1300),
    (CHANKA, "chanka", 2582, 2890),
)
LEGAL_TERMS = frozenset(
    """abogado acusacion agresor agresion alimentos apelar audiencia casado casada denuncia derecho divorcio
    esposa esposo familia fiscal hija hijo hijos juez juicio justicia ley madre maltrato matrimonio menor nina nino
    padre pension prueba sentencia separacion testigo victima violacion violencia viuda viudo""".split()
)
MAX_ARTICLE_CHARS = 1500
_ROLE = re.compile(r"^(?:[FCA]\s+)+(?=\S)")
_SEPARATOR = re.compile(r"^\|[-| :]+\|$")
_MID_CAPITAL = re.compile(r"[a-zñ'’.,;]\s+[A-ZÑ¿¡]")


def clean_cell(cell: str) -> str:
    cell = re.sub(r"\s+", " ", cell).strip()
    cell = re.sub(r"(\w)- (\w)", r"\1\2", cell)
    return _ROLE.sub("", cell).strip()


def table_rows(text: str, start: int, end: int):
    for number, line in enumerate(text.split("\n")[start - 1 : end], start):
        if line.startswith("|") and not _SEPARATOR.match(line):
            cells = [clean_cell(c) for c in line.strip().strip("|").split("|")]
            cells = [c for c in cells if c and c not in {"F", "C", "A", "C C"}]
            yield number, cells


def _alternatives(cell: str) -> list:
    return [part.strip() for part in re.split(r"\s*/\s*", cell) if part.strip()]


def _is_clean_sentence(es: str, qu: str) -> bool:
    if _MID_CAPITAL.search(re.sub(r"[¿¡]", "", es)) or _MID_CAPITAL.search(re.sub(r"[¿¡]", "", qu)):
        return False
    return qu.count("¿") <= es.count("¿") and qu.count("¡") <= es.count("¡")


def sentence_pairs(files):
    out, dropped = [], Counter()
    for name, variant, start, end, label in SENTENCE_SECTIONS:
        text = files[name]
        for number, cells in table_rows(text, start, end):
            if len(cells) != 2:
                dropped["filas con columnas irregulares"] += 1
                continue
            es, qu = cells
            if len(tokens(es)) < 2 or detect_language(es) == "qu" or detect_language(qu) == "es":
                dropped["idioma incoherente"] += 1
                continue
            if not _is_clean_sentence(es, qu):
                dropped["alternativas o varias oraciones"] += 1
                continue
            prefix = "cc" if variant == "cusco-collao" else "ch"
            out.append(_pair(f"{prefix}-l{number}", "sentence", variant, es, _alternatives(qu), name,
                             f"línea {number} ({label})"))
    return out, dropped


def term_pairs(files):
    out, seen = [], set()
    for name, variant, start, end in TERM_SECTIONS:
        for number, cells in table_rows(files[name], start, end):
            if len(cells) != 2 or _MID_CAPITAL.search(cells[0]) or len(tokens(cells[0])) > 3:
                continue
            es, qu = cells
            key = fold(es).strip(" ,.")
            if key not in LEGAL_TERMS and not (len(tokens(es)) == 1 and fold(tokens(es)[0]) in LEGAL_TERMS):
                continue
            if tokens(es)[0] in SPANISH_STOPWORDS and len(tokens(es)) > 1 and False:
                continue
            references = [r for r in re.split(r"\s*[,/;]\s*", qu) if r and not _MID_CAPITAL.search(r)]
            if not references or (variant, key) in seen:
                continue
            seen.add((variant, key))
            prefix = "cc" if variant == "cusco-collao" else "ch"
            out.append(_pair(f"term-{prefix}-l{number}", "term", variant, es, references, name, f"línea {number}"))
    return out


def article_pairs(files):
    text = strip_page_noise(files[LEY])
    quechua = {m.group(1): m.start() for m in re.finditer(r"^## (\d+(?:-[A-Z])?) Phatmi\.", text, re.M)}
    spanish = [(m.group(1), m.group(2).strip(), m.start(), m.end()) for m in
               re.finditer(r"^## Artículo (\d+(?:-[A-Z])?)\. (.+)$", text, re.M)]
    heading_positions = sorted({m.start() for m in re.finditer(r"^## (?:\d+(?:-[A-Z])? Phatmi\.|Artículo \d|TÍTULO|CAPÍTULO)", text, re.M)})
    out = []
    for number, title, start, end in spanish:
        if number not in quechua:
            continue
        nxt = next((p for p in heading_positions if p > start), len(text))
        es_body = _paragraphs(text[end:nxt])
        qu_start = quechua[number]
        qu_next = next((p for p in heading_positions if p > qu_start), len(text))
        qu_block = text[qu_start:qu_next].split("\n", 1)
        qu_title = re.sub(r"^## \S+ Phatmi\.\s*", "", qu_block[0]).strip()
        qu_body = _paragraphs(qu_block[1] if len(qu_block) > 1 else "")
        body_es, body_qu = " ".join(es_body), " ".join(qu_body)
        if not es_body or len(es_body) != len(qu_body) or len(body_es) > MAX_ARTICLE_CHARS:
            continue
        if not 0.6 <= len(body_qu) / len(body_es) <= 1.8 or detect_language(body_qu) != "qu":
            continue
        slug = number.lower()
        out.append(_pair(f"ley-art-{slug}", "article", "sureno-sin-confirmar", "\n\n".join(es_body), ["\n\n".join(qu_body)],
                         LEY, f"Artículo {number}"))
        if qu_title and title and detect_language(qu_title) != "es":
            out.append(_pair(f"ley-titulo-{slug}", "title", "sureno-sin-confirmar", title, [qu_title], LEY,
                             f"Encabezado del artículo {number}"))
    return out


def _paragraphs(block: str) -> list:
    return [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", block) if re.sub(r"[#\s]", "", p) and not p.lstrip().startswith("#")]


def _split(pair_id: str) -> str:
    return "holdout" if int(hashlib.sha1(pair_id.encode()).hexdigest()[:4], 16) % 10 < 3 else "dev"


def _pair(pair_id, kind, variant, es, references, origin_file, locator):
    return TranslationPair(
        id=pair_id, version=1, status="candidate", reviewers=[], kind=kind, variant=variant,
        reference_quality="clean", source_es=es, references_qu=references,
        origin={"file": origin_file, "locator": locator}, split=_split(pair_id),
        notes="Candidato extraído de texto impreso; pendiente de revisión por hablantes nativos.",
    )


def build_seed(sources_dir=SOURCES_DIR):
    files = {name: Path(sources_dir, name).read_text(encoding="utf-8") for name in (CUSCO, CHANKA, LEY)}
    sentences, dropped = sentence_pairs(files)
    pairs = sentences + term_pairs(files) + article_pairs(files)
    problems = [p for pair in pairs for p in verify_pair(pair, sources_dir)]
    if problems:
        raise ValueError("Semilla inválida:\n- " + "\n- ".join(problems[:20]))
    return pairs, dropped


if __name__ == "__main__":
    built, discarded = build_seed()
    dump_pairs(built, TRANSLATION_PATH)
    counts = Counter((p.kind, p.variant) for p in built)
    print(f"{len(built)} pares candidatos escritos en {TRANSLATION_PATH}")
    print(dict(counts))
    print("descartados:", dict(discarded))
