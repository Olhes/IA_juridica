"""Parser determinista de estructura *candidata*, no intérprete de vigencia.

Los offsets son caracteres Unicode [start,end) del Markdown exacto. Los rangos
AST contienen hijos; ``segments`` es la partición sin overlap del texto canónico.
Solo etiquetas se normalizan: nunca se corrige/reconstruye el texto de evidencia.
"""

from bisect import bisect_right
from collections import Counter
from copy import deepcopy
import hashlib
import heapq
import json
import re
import unicodedata

from ingestion.structure_review import reviewed_lines

PARSER_VERSION = "pe-structural-candidate-v2"


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fold(text):
    return "".join(
        c
        for c in unicodedata.normalize("NFD", text.lower())
        if not unicodedata.combining(c)
    )


def _clean(line):
    text = re.sub(r"^\s*#{1,6}\s+", "", line.strip())
    return text.strip().strip("*_ ").strip()


_INSTRUMENT = re.compile(
    r"^(ley|decreto (?:supremo|legislativo|de urgencia)|"
    r"resolucion (?:ministerial|suprema|administrativa))\s+"
    r"(?:n(?:ro)?[.°ºo]*\s*)?(\d[\w./-]*)(?:\s*[:.-]\s+.+)?$"
)
_LEVELS = {
    "libro": 20,
    "titulo": 30,
    "capitulo": 40,
    "subcapitulo": 45,
    "seccion": 50,
    "subseccion": 55,
}
_HIERARCHY = re.compile(
    r"^(libro|titulo|capitulo|subcapitulo|seccion|subseccion)\s+"
    r"(preliminar|unico|[ivxlcdm]+|\d+[a-z-]*)(?=$|[\s.°º:\-])"
)
_ARTICLE = re.compile(
    r"^(?:articulo|art\.)\s+(unico|[ivxlcdm]+|\d+(?:-[a-z]+|[a-z])?)"
    r"(?=$|[\s.°º:\-])"
)
_ORDINAL = re.compile(
    r"^(unica|primera|segunda|tercera|cuarta|quinta|sexta|septima|octava|"
    r"novena|decima(?:\s+\w+)?|undecima|duodecima|vigesima(?:\s+\w+)?|"
    r"trigesima(?:\s+\w+)?)(?=[.\-:\s]|$)"
)
_GROUP = re.compile(
    r"^disposiciones?\s+(?:(?:complementarias?|finales?|transitorias?|"
    r"derogatorias?|modificatorias?)\s*)+$"
)
_SINGLE_DISPOSITION = re.compile(
    r"^disposicion\s+(?:(?:complementaria|final|transitoria|derogatoria|modificatoria)\s+)+(.+)$"
)
_NUMERAL = re.compile(r"^(\d+(?:\.\d+)*)(?:\.-?|[)\-])?\s+\S")
_INCISO = re.compile(r"^(?:[-*]\s+)?([a-z]|[ivxlcdm]{2,})[).]\s+\S")
_AMEND = re.compile(
    r"\b(?:modific\w*|incorpor\w*|sustituy\w*|sustitu\w*)\b.*"
    r"(?:siguiente(?:s)?\s+(?:texto|terminos)|queda\w*\s+redactad|texto\s+siguiente)"
)


def _protected(text, lines):
    """Code fences y citas no son artículos del instrumento contenedor."""
    regions, diagnostics = [], []
    fence, fence_start = None, None
    block_start, block_end = None, None
    code = []
    for start, end, line in lines:
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker and fence is None:
            fence, fence_start = marker[1], start
        elif fence is not None:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                code.append((fence_start, end))
                fence = None
        if fence is not None or (code and code[-1][0] <= start < code[-1][1]):
            continue
        if line.lstrip().startswith(">"):
            if block_start is None:
                block_start = start
            block_end = end
        elif block_start is not None:
            regions.append((block_start, block_end, "blockquote"))
            block_start = None
    if fence is not None:
        code.append((fence_start, len(text)))
        diagnostics.append({"code": "unclosed_code_fence", "start": fence_start})
    if block_start is not None:
        regions.append((block_start, block_end, "blockquote"))
    excluded = sorted([*code, *((a, b) for a, b, _ in regions)])
    cursor = 0
    opened, quote_start = None, None
    closing = {"«": "»", "“": "”", '"': '"'}
    for index, char in enumerate(text):
        while cursor < len(excluded) and excluded[cursor][1] <= index:
            cursor += 1
        if (
            cursor < len(excluded)
            and excluded[cursor][0] <= index < excluded[cursor][1]
        ):
            continue
        if char == '"' and index and text[index - 1] == "\\":
            continue
        if opened is not None:
            if char == closing[opened]:
                regions.append((quote_start, index + 1, "quotation"))
                opened = None
        elif char in closing:
            opened, quote_start = char, index
    if opened is not None:
        regions.append((quote_start, len(text), "unclosed_quotation"))
        diagnostics.append({"code": "unclosed_quotation", "start": quote_start})
    regions.sort()
    return regions, code, diagnostics


def _partition(text, nodes):
    """Sweep de rangos anidados; cada carácter tiene un solo propietario."""
    events = {}
    for node in nodes:
        if node["end"] > node["start"]:
            events.setdefault(node["start"], []).append((True, node))
            events.setdefault(node["end"], []).append((False, node))
    positions, active, heap, segments = sorted(events), set(), [], []
    for start, end in zip(positions, positions[1:]):
        for entering, node in events[start]:
            if entering:
                active.add(node["id"])
                heapq.heappush(heap, (-node["depth"], -node["start"], node["id"]))
            else:
                active.discard(node["id"])
        while heap and heap[0][2] not in active:
            heapq.heappop(heap)
        owner = heap[0][2]
        if segments and segments[-1]["owner"] == owner:
            segments[-1]["end"] = end
        else:
            segments.append({"start": start, "end": end, "owner": owner})
    for segment in segments:
        segment["text_sha256"] = _hash(text[segment["start"] : segment["end"]])
    return segments


def align_docling(markdown, document):
    """Alineación exacta y única; ``prov.charspan`` sigue siendo local al item.

    No se buscan textos normalizados ni se adivina geometría de tablas. El JSON
    original se guarda aparte, incluso para items sin correspondencia Markdown.
    """
    if document is None:
        return [], [{"code": "docling_layout_unavailable"}]
    if not isinstance(document, dict):
        raise ValueError("El artefacto Docling debe ser un objeto JSON")
    # Rechazar objetos Python/NaN: el hash debe representar JSON reproducible.
    json.dumps(document, allow_nan=False)
    mappings, diagnostics = [], []
    texts = document.get("texts", [])
    if not isinstance(texts, list):
        raise ValueError("Docling texts debe ser una lista")
    occurrences = Counter(
        item.get("text")
        for item in texts
        if isinstance(item, dict) and isinstance(item.get("text"), str)
    )
    for index, item in enumerate(texts):
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            diagnostics.append({"code": "invalid_docling_text_item", "item": index})
            continue
        text = item["text"]
        first = markdown.find(text) if text else -1
        second = markdown.find(text, first + 1) if first >= 0 else -1
        status = (
            "unique"
            if first >= 0 and second < 0 and occurrences[text] == 1
            else "ambiguous" if first >= 0 else "unmapped"
        )
        mapping = {
            "item": index,
            "self_ref": item.get("self_ref"),
            "status": status,
            "text_sha256": _hash(text),
            "prov": deepcopy(item.get("prov", [])),
            "prov_charspan_space": "docling_item_text",
        }
        if status == "unique":
            mapping.update(start=first, end=first + len(text))
        else:
            diagnostics.append({"code": f"docling_text_{status}", "item": index})
        mappings.append(mapping)
    return mappings, diagnostics


def parse_legal_structure(
    markdown: str, docling_document: dict | None = None, *, documentary_review=None
) -> dict:
    """Sugerir AST jurídico peruano; todas las identidades requieren revisión."""
    if not isinstance(markdown, str):
        raise TypeError("Markdown debe ser texto")
    source_hash = _hash(markdown)
    lines, offset = [], 0
    for line in markdown.splitlines(keepends=True):
        lines.append((offset, offset + len(line), line))
        offset += len(line)
    regions, code, diagnostics = _protected(markdown, lines)
    protected = []
    for a, b in sorted([*((a, b) for a, b, _ in regions), *code]):
        if protected and a <= protected[-1][1]:
            protected[-1] = (protected[-1][0], max(b, protected[-1][1]))
        else:
            protected.append((a, b))
    starts = [a for a, _ in protected]

    def is_protected(position):
        index = bisect_right(starts, position) - 1
        return index >= 0 and position < protected[index][1]

    lines, boundaries, review = reviewed_lines(markdown, lines, documentary_review)
    for boundary in boundaries.values():
        if any(boundary.start < b and a < boundary.end for a, b in protected):
            raise ValueError("Corrección documental dentro de una cita o código")

    def node(kind, number, label, start, heading_end, parent, rank):
        identity = "node:" + _hash(f"{source_hash}:{kind}:{start}:{heading_end}")
        part = _fold(
            label if kind == "instrument" else f"{kind}-{number or 'sin-numero'}"
        )
        part = re.sub(r"[^a-z0-9-]+", "-", part).strip("-")
        return {
            "id": identity,
            "parent_id": parent["id"] if parent else None,
            "kind": kind,
            "number": number,
            "label": label,
            "start": start,
            "end": len(markdown),
            "heading_end": heading_end,
            "depth": parent["depth"] + 1 if parent else 0,
            "rank": rank,
            "component_suggestion": (
                f"{parent['component_suggestion']}/{part}" if parent else "document"
            ),
            "provenance_state": "unverified",
            "review_required": True,
        }

    root = node("document", None, "Documento candidato", 0, 0, None, 0)
    nodes, stack, seen = [root], [root], set()
    amendment_host = None
    for start, end, line in lines:
        label = _clean(line)
        folded = _fold(label)
        content_start = start + len(line) - len(line.lstrip())
        content_start += len(re.match(r"(?:#{1,6}\s+)?[*_]*", line.lstrip())[0])
        if not label:
            continue
        if is_protected(content_start):
            if any(a <= content_start < b for a, b, _ in regions):
                amendment_host = None
            continue
        if line.lstrip().startswith("|"):
            diagnostics.append({"code": "table_requires_layout_review", "start": start})
            continue
        if re.search(r"\.{3,}\s*\d+\s*$", label):
            diagnostics.append({"code": "toc_entry_skipped", "start": start})
            continue
        kind, number, rank = None, None, None
        instrument = _INSTRUMENT.match(folded)
        hierarchy = _HIERARCHY.match(folded)
        article = _ARTICLE.match(folded)
        group = _GROUP.fullmatch(folded)
        single = _SINGLE_DISPOSITION.match(folded)
        ordinal = _ORDINAL.match(folded)
        legal_host = next(
            (n for n in reversed(stack) if n["kind"] in {"article", "disposition"}),
            None,
        )
        if start in boundaries:
            kind, rank = "instrument", 10
            diagnostics.append(
                {"code": "documentary_instrument_boundary", "start": start}
            )
        elif instrument or re.fullmatch(
            r"codigo (?:penal|civil|procesal (?:penal|civil)|de los ninos y adolescentes)",
            folded,
        ):
            number = instrument[2] if instrument else None
            active = next((n for n in stack if n["kind"] == "instrument"), None)
            if active and _fold(active["label"]) == folded:
                diagnostics.append(
                    {"code": "repeated_instrument_heading", "start": start}
                )
                continue
            kind, rank = "instrument", 10
        elif hierarchy:
            kind, number = hierarchy[1], hierarchy[2]
            rank = _LEVELS[kind]
        elif single and _ORDINAL.match(single[1]):
            kind, number, rank = "disposition", _ORDINAL.match(single[1])[1], 70
        elif group:
            kind, rank = "disposition_group", 60
        elif article:
            kind, number, rank = "article", article[1], 70
            if amendment_host is not None:
                kind, rank = "amendment_payload", 75
                diagnostics.append(
                    {"code": "unquoted_amendment_boundary_ambiguous", "start": start}
                )
        elif ordinal and any(n["kind"] == "disposition_group" for n in stack):
            kind, number, rank = "disposition", ordinal[1], 70
        elif legal_host is not None:
            numeral, inciso = _NUMERAL.match(folded), _INCISO.match(folded)
            if numeral:
                kind, number = "numeral", numeral[1]
                rank = 80 + min(number.count("."), 15)
            elif inciso:
                kind, number, rank = "inciso", inciso[1], 100
                if len(number) > 1 and any(n["kind"] == "inciso" for n in stack):
                    kind, rank = "subinciso", 110
        if kind is not None:
            if rank <= 60:
                amendment_host = None
            while len(stack) > 1 and stack[-1]["rank"] >= rank:
                stack.pop()["end"] = start
            if kind == "numeral" and "." in number:
                prefix = number.rsplit(".", 1)[0]
                while stack[-1]["kind"] == "numeral" and stack[-1]["number"] != prefix:
                    stack.pop()["end"] = start
                if stack[-1]["kind"] != "numeral" and not (
                    stack[-1]["kind"] == "article" and stack[-1]["number"] == prefix
                ):
                    diagnostics.append(
                        {
                            "code": "missing_numeral_parent",
                            "start": start,
                            "number": number,
                        }
                    )
            parent = stack[-1]
            key = (parent["id"], kind, number)
            if key in seen:
                diagnostics.append(
                    {
                        "code": "duplicate_heading",
                        "start": start,
                        "kind": kind,
                        "number": number,
                    }
                )
            seen.add(key)
            new = node(kind, number, label, start, end, parent, rank)
            nodes.append(new)
            stack.append(new)
        host = next(
            (n for n in reversed(stack) if n["kind"] in {"article", "disposition"}),
            None,
        )
        if (
            host
            and _AMEND.search(folded)
            and not any(start <= a < end for a, _, _ in regions)
        ):
            amendment_host = host["id"]
    # Las citas se adjuntan al componente contenedor, nunca como artículos host.
    for start, end, reason in regions:
        text = markdown[start:end]
        if (
            reason == "quotation"
            and "\n" not in text
            and not _ARTICLE.match(_fold(_clean(text[1:-1])))
        ):
            continue
        parent = max(
            (n for n in nodes if n["start"] <= start and n["end"] >= end),
            key=lambda n: n["depth"],
        )
        payload = node("quoted_payload", None, reason, start, start, parent, 120)
        payload["end"] = end
        nodes.append(payload)
    for item in nodes:
        item["text_sha256"] = _hash(markdown[item["start"] : item["end"]])
        del item["rank"]
    mappings, layout_diagnostics = align_docling(markdown, docling_document)
    return {
        "schema_version": 1,
        "parser_version": PARSER_VERSION,
        "markdown_sha256": source_hash,
        "offset_space": "unicode_codepoints",
        "provenance_state": "unverified",
        "review_required": True,
        "documentary_review": review,
        "nodes": nodes,
        "segments": _partition(markdown, nodes),
        "docling_mappings": mappings,
        "diagnostics": diagnostics + layout_diagnostics,
    }
