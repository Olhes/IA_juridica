"""Segmentación reproducible del TUO de El Peruano y de la Ley 32006.

Los límites y el inventario se contrastan con la edición fijada, no se
nombran artículos por similitud ni se reconstruye su vigencia con un LLM.
"""

from hashlib import sha256
from io import BytesIO
import re

from pypdf import PdfReader


CPC = "pe:dl:768"
LAW = "pe:ley:32006"
CPC_URL = "https://diariooficial.elperuano.pe/Normas/obtenerDocumento?idNorma=120007"
LAW_URL = "https://busquedas.elperuano.pe/dispositivo/NL/2282515-2"
CPC_PDF = "pe-dl-768-tuo-el-peruano.pdf"
LAW_PDF = "pe-ley-32006-el-peruano.pdf"
CPC_HASH = "d7552e506c51e2ca3f48bc2221ae61d21e972c79e4fae387350955df29541e4e"
LAW_HASH = "83fc47e799a7cd53d00e93e3db6ff43afc6e3b94158a0a15da702f5cebc8c9ef"

_ROMAN = "I II III IV V VI VII VIII IX X".split()
_SUFFIXED = "119-A 392-A 506-A 523-A 565-A 566-A 647-A 690-A 690-B 690-C 690-D 690-E 690-F 692-A 705-A".split()
_CP_HEADER = ["Inicio", "NORMAS LEGALES ACTUALIZADAS", "TUO del Código Procesal Civil", "TUO del Código Procesal Civil"]
_ARTICLE = re.compile(r'^[“"«]?Artículo\s+(\d+(?:\s*-\s*[A-Z]+)?|[IVX]+)[º°]?\s*\.\s*-?\s*(.*)$')
_REPEALED = re.compile(r"^Artículos (\d+) (?:a|y) (\d+)\.\-\s*\(\s*\*\s*\)\s*Artículos derogados")
_STRUCTURE = re.compile(r'^[“"]?(SECCIÓN|TÍTULO|CAPÍTULO|Subcapítulo)\s+'
                        r'([IVXLCDM]+|\d+|PRELIMINAR|PRIMERA|SEGUNDA|TERCERA|CUARTA|QUINTA|SEXTA)\b')
_DISPOSITION = re.compile(r'^[“"]?(?:Primera|Segunda|Tercera|Cuarta|Quinta|Sexta|S[eé]tima|Séptima|Octava|Novena|(?:Décimo|Décima|Vigésima|Vigésimo)(?:\s+\w+)?|Única)\s*\.\s*-', re.I)
_GROUP = re.compile(r"^DISPOSICIONES (COMPLEMENTARIAS|FINALES|TRANSITORIAS|MODIFICATORIAS|DEROGATORIAS)$")
_PART = re.compile(r"(?m)^(\d+|[a-zñ])[.)]\s+")
_NOTE = re.compile(r'(?m)^(?:\(\s*\*\s*\))|[”»]\s+\(\s*\*\s*\)')


def _pages(pdf, expected_hash, page_count):
    if sha256(pdf).hexdigest() != expected_hash:
        raise ValueError("El PDF no es la edición oficial cotejada")
    pages = PdfReader(BytesIO(pdf)).pages
    if len(pages) != page_count:
        raise ValueError("Página faltante en la fuente oficial")
    return [page.extract_text().splitlines() for page in pages]


def _line(line):
    # El PDF incluye espacios medios y ligaduras tipográficas, no cambios jurídicos.
    return " ".join(line.translate(str.maketrans({"ﬁ": "fi", "ﬂ": "fl", "\u00ad": None})).split())


def _add_sequential_parts(edition, article, text):
    # Una enumeración simple tiene un único estilo y reinicia en 1 o a.
    # Las listas anidadas siguen en el texto íntegro: se evita inventar su árbol.
    body_end = _NOTE.search(text)
    limit = body_end.start() + int(body_end[0].startswith(('”', '»'))) if body_end else len(text)
    parts = list(_PART.finditer(text, 0, limit))
    markers = [p[1] for p in parts]
    if len(markers) < 2:
        return
    if markers == [str(i) for i in range(1, len(markers) + 1)]:
        kind = "numeral"
    elif markers == list(("abcdefghijklmnñopqrstuvwxyz" if "ñ" in markers else "abcdefghijklmnopqrstuvwxyz")[:len(markers)]):
        kind = "inciso"
    else:
        return
    for i, part in enumerate(parts):
        end = parts[i + 1].start() if i + 1 < len(parts) else limit
        label = part[1] + ("." if kind == "numeral" else ")")
        node = edition.add(kind, label, parent=article["id"], identity=f"{article['id']}-{kind}-{part[1]}")
        node.update(start=article["start"] + part.start(), end=article["start"] + part.start() + len(text[part.start():end].rstrip()))


class _Edition:
    def __init__(self, title):
        self.markdown = ""
        self.components = []
        self.root = self.add("document", title, parent=None)

    def add(self, kind, label, *, parent, identity=None):
        component = {"id": identity or f"new:{len(self.components)}", "kind": kind,
                     "label": label, "start": len(self.markdown), "end": 0, "parent_id": parent}
        self.components.append(component)
        return component

    def write(self, text):
        self.markdown += text.rstrip() + "\n\n"

    def close(self, component):
        component["end"] = len(self.markdown)

    def build(self):
        self.close(self.root)
        return self.markdown.rstrip() + "\n\n", self.components


def parse_cpc(pdf):
    cover, *rest = _pages(pdf, CPC_HASH, 98)
    if "07/06/2025" not in cover:
        raise ValueError("La portada no identifica la edición auditada")
    lines = []
    for number, page in enumerate(rest, 2):
        if page[:5] != [str(number), *_CP_HEADER]:
            raise ValueError(f"Cambio de cabecera en página {number}")
        lines.extend(filter(None, map(_line, page[5:])))
    first = next(i for i, line in enumerate(lines) if line.startswith("Artículo I.-"))
    start = first - 1  # Excluir el índice y la RM de aprobación de la numeración propia del CPC.
    if lines[start] != "TÍTULO PRELIMINAR":
        raise ValueError("Límite del Título Preliminar no reconocido")
    edition = _Edition("Código Procesal Civil — TUO oficial")
    edition.write("# Código Procesal Civil — TUO oficial\n\n" + "\n".join(lines[:start]))
    hierarchy = []
    article_ids = []
    appendix = None
    controls = []
    for i, line in enumerate(lines[start:], start):
        if group := _GROUP.fullmatch(line):
            appendix = group[1]
            controls.append((i, "group", appendix))
        elif appendix:
            if appendix in {"FINALES", "TRANSITORIAS"} and _DISPOSITION.match(line):
                controls.append((i, "disposition", None))
        elif heading := _STRUCTURE.match(line):
            controls.append((i, "structure", heading[1]))
        elif heading := _REPEALED.match(line):
            first, last = map(int, heading.groups())
            controls.append((i, "repealed", list(map(str, range(first, last + 1)))))
        elif heading := _ARTICLE.match(line):
            controls.append((i, "article", re.sub(r"\s", "", heading[1])))

    for (i, kind, value), (end, _, _) in zip(controls, [*controls[1:], (len(lines), "", None)]):
        text = "\n".join(lines[i:end])
        ranks = {"SECCIÓN": 10, "TÍTULO": 20, "CAPÍTULO": 30, "Subcapítulo": 40}
        if kind in {"group", "structure"}:
            depth = ranks[value] if kind == "structure" else (10 if value == "COMPLEMENTARIAS" else 20)
            while hierarchy and hierarchy[-1][0] >= depth:
                edition.close(hierarchy.pop()[1])
            node = edition.add({"SECCIÓN":"seccion", "TÍTULO":"titulo", "CAPÍTULO":"capitulo",
                                "Subcapítulo":"subcapitulo"}.get(value, "disposition_group"),
                               lines[i].strip('“”"'), parent=(hierarchy[-1][1] if hierarchy else edition.root)["id"])
            hierarchy.append((depth, node))
            edition.write("## " + text)
            continue
        parent = (hierarchy[-1][1] if hierarchy else edition.root)["id"]
        if kind == "repealed":
            # Cada número del rango resuelve a la constancia, nunca al texto derogado.
            for number in value:
                node = edition.add("article", f"Artículo {number}.- Derogado", parent=parent,
                                   identity=f"new:cpc-{number.lower()}")
                edition.write(text)
                edition.close(node)
                article_ids.append(number)
            continue
        if kind == "article":
            article_ids.append(value)
            label = f"Artículo {value}.- {_ARTICLE.match(lines[i])[2]}".strip()
            node = edition.add("article", label, parent=parent, identity=f"new:cpc-{value.lower()}")
            # Mantener el cuerpo y la nota de la edición; no confundir una nota
            # de modificación de un numeral con derogación de todo el artículo.
            edition.write(text)
            _add_sequential_parts(edition, node, text)
        else:
            node = edition.add("disposition", lines[i], parent=parent)
            edition.write(text)
        edition.close(node)
    for _, node in reversed(hierarchy):
        edition.close(node)

    expected = [*_ROMAN, *(str(n) for n in range(1, 848))]
    for key in _SUFFIXED:
        # Lista positiva de todas las adiciones en la edición cotejada.
        position = expected.index(key.split('-')[0]) + 1
        while position < len(expected) and expected[position].startswith(key.split('-')[0] + "-"):
            position += 1
        expected.insert(position, key)
    if article_ids != expected:
        missing = sorted(set(expected) - set(article_ids))
        raise ValueError(f"Inventario CPC inesperado: {len(article_ids)} artículos, faltan {missing}, orden/duplicados por revisar")
    return edition.build()


def parse_law_32006(pdf):
    pages = _pages(pdf, LAW_HASH, 2)
    body = [line for line in map(_line, pages[0]) if line]
    # El segundo folio empieza con la continuación del artículo y las finales.
    second = [line for line in map(_line, pages[1]) if line]
    start = second.index("este supuesto, esta información es presentada en")
    second = second[start:second.index("2282515-2")]
    law = [*body[body.index("LEY Nº 32006"):], *second]
    edition = _Edition("Ley 32006 — publicación oficial")
    controls = [next(i for i, line in enumerate(law) if line.startswith(prefix)) for prefix in (
        "Artículo único", "DISPOSICIONES COMPLEMENTARIAS", "PRIMERA.", "SEGUNDA.", "TERCERA.",
        "DISPOSICIÓN COMPLEMENTARIA", "ÚNICA. Derogación", "POR TANTO:")]
    edition.write("\n".join(law[:controls[0]]))
    for idx, (a, b) in enumerate(zip(controls, controls[1:])):
        if idx in {1, 5}:
            edition.write("\n".join(law[a:b]))
            continue
        label = "Artículo único.- Modificación del artículo 564 del Código Procesal Civil" if idx == 0 else law[a]
        node = edition.add("article" if idx == 0 else "disposition", label, parent=edition.root["id"])
        edition.write("\n".join(law[a:b]))
        edition.close(node)
    edition.write("\n".join(law[controls[-1]:]))
    return edition.build()
