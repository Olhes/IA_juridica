"""Deterministic Unicode-codepoint evidence localization and RDF-star export."""
from __future__ import annotations

from hashlib import sha256
import json
import re
import unicodedata

from services.graphragprov.models import (
    CharSpan,
    DEFAULT_NAMESPACES,
    GroundedGraph,
    LocalizedSpans,
    RDFTerm,
    RDF_TYPE_IRI,
    SpanMatchQuality,
    StatementOccurrence,
    XSD_INTEGER_IRI,
)

TEXTPROV_NS = DEFAULT_NAMESPACES["textprov"]

_ABBREV_END_RE = re.compile(
    r"(?:\b(?:art|arts|inc|num|lit|cap|tit|disp|ley|d\.l|d\.s|r\.m|n|nro)\.|n°)$",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[0-9A-Za-zÀ-ÿÑñ]+")
_SPAN_QUALITY_PENALTY: dict[SpanMatchQuality, int] = {
    "exact": 0,
    "normalized": 1,
    "anchored": 2,
    "clause_window": 2,
    "inferred_from_heading": 1,
}


def mint_occurrence_token(
    doc_id: str,
    component_id: str,
    start: int,
    end: int,
    subject: RDFTerm,
    predicate: RDFTerm,
    obj: RDFTerm,
) -> str:
    """Return deterministic 'occ_' + sha256(canonical(...))[:12]."""
    payload = json.dumps(
        [
            doc_id,
            component_id,
            start,
            end,
            subject.ntriples(),
            predicate.ntriples(),
            obj.ntriples(),
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "occ_" + sha256(payload.encode("utf-8")).hexdigest()[:12]


def _fold_with_map(text: str) -> tuple[str, list[int]]:
    """Fold text (NFD diacritic strip, casefold, whitespace collapse) with monotonic codepoint map."""
    folded_chars: list[str] = []
    idx_map: list[int] = []
    in_ws = False
    for idx, ch in enumerate(text):
        if ch.isspace():
            if not in_ws and folded_chars:
                folded_chars.append(" ")
                idx_map.append(idx)
            in_ws = True
            continue
        in_ws = False
        decomposed = unicodedata.normalize("NFD", ch)
        for piece in decomposed:
            if unicodedata.category(piece) == "Mn":
                continue
            for lowered in piece.casefold():
                folded_chars.append(lowered)
                idx_map.append(idx)
    if folded_chars and folded_chars[-1] == " ":
        folded_chars.pop()
        idx_map.pop()
    return "".join(folded_chars), idx_map


def _fold_plain(text: str) -> str:
    folded, _ = _fold_with_map(text)
    return folded


def _split_clauses(text: str) -> list[tuple[int, int]]:
    """Split component text into trimmed sentence/clause codepoint windows."""
    if not text or not text.strip():
        return []
    windows: list[tuple[int, int]] = []
    n = len(text)
    start = 0
    i = 0
    while i < n:
        ch = text[i]
        boundary = False
        if ch == "\n":
            boundary = True
        elif ch in ".;!?" and (i + 1 == n or text[i + 1].isspace()):
            prefix = text[start : i + 1].rstrip()
            if ch != "." or not _ABBREV_END_RE.search(prefix):
                boundary = True
        if boundary:
            seg_end = i + 1 if ch != "\n" else i
            trimmed = _trim_window(text, start, seg_end)
            if trimmed is not None:
                windows.append(trimmed)
            start = i + 1
        i += 1
    if start < n:
        trimmed = _trim_window(text, start, n)
        if trimmed is not None:
            windows.append(trimmed)
    full = _trim_window(text, 0, n)
    if full is not None and full not in windows:
        windows.append(full)
    return windows


def _trim_window(text: str, start: int, end: int) -> tuple[int, int] | None:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    if end <= start:
        return None
    return (start, end)


def _find_role_candidates(
    text: str,
    window: tuple[int, int],
    needle: str,
    *,
    allow_anchored: bool = True,
    max_hits: int = 8,
) -> list[CharSpan]:
    """Locate candidate spans inside window via exact -> normalized -> anchored strategies."""
    query = needle.strip()
    if not query:
        return []
    w_start, w_end = window
    segment = text[w_start:w_end]
    hits: list[CharSpan] = []
    seen_bounds: set[tuple[int, int]] = set()

    def add_hit(local_s: int, local_e: int, quality: SpanMatchQuality) -> None:
        g_s, g_e = w_start + local_s, w_start + local_e
        if g_e <= g_s or (g_s, g_e) in seen_bounds:
            return
        surface = text[g_s:g_e]
        if not surface.strip():
            return
        seen_bounds.add((g_s, g_e))
        hits.append(CharSpan(start=g_s, end=g_e, surface_text=surface, quality=quality))

    # Stage 1a: exact case-sensitive match
    pos = segment.find(query)
    while pos != -1 and len(hits) < max_hits:
        add_hit(pos, pos + len(query), "exact")
        pos = segment.find(query, pos + 1)

    # Stage 1b: exact case-insensitive same-length match (safe when lower preserves codepoint length)
    if not hits:
        seg_lower = segment.lower()
        q_lower = query.lower()
        if len(seg_lower) == len(segment) and len(q_lower) == len(query):
            pos = seg_lower.find(q_lower)
            while pos != -1 and len(hits) < max_hits:
                add_hit(pos, pos + len(query), "exact")
                pos = seg_lower.find(q_lower, pos + 1)

    # Stage 2: folded NFD/diacritic/whitespace-collapsed match via monotonic codepoint map
    if not hits:
        folded_seg, idx_map = _fold_with_map(segment)
        folded_q = _fold_plain(query)
        if folded_q:
            pos = folded_seg.find(folded_q)
            while pos != -1 and len(hits) < max_hits:
                orig_start = idx_map[pos]
                last_folded = pos + len(folded_q) - 1
                orig_end = idx_map[last_folded] + 1
                # Include trailing combining marks attached to the final codepoint.
                while orig_end < len(segment) and unicodedata.category(segment[orig_end]) == "Mn":
                    orig_end += 1
                add_hit(orig_start, orig_end, "normalized")
                pos = folded_seg.find(folded_q, pos + 1)

    # Stage 3: token-anchored fallback for inflected phrases or minor punctuation drift
    if not hits and allow_anchored:
        q_tokens = [_fold_plain(tok) for tok in _WORD_RE.findall(query)]
        q_tokens = [tok for tok in q_tokens if len(tok) >= 3]
        if q_tokens:
            seg_tokens = [
                (_fold_plain(m.group(0)), m.start(), m.end())
                for m in _WORD_RE.finditer(segment)
            ]
            # Find shortest contiguous slice in seg_tokens containing all query tokens (or longest prefix).
            for target_len in (len(q_tokens), max(1, len(q_tokens) - 1)):
                required = set(q_tokens[:target_len])
                best_span: tuple[int, int, int] | None = None
                for i in range(len(seg_tokens)):
                    matched: set[str] = set()
                    for j in range(i, min(len(seg_tokens), i + target_len + 6)):
                        tok_text = seg_tokens[j][0]
                        for req in required:
                            if tok_text == req or (len(req) >= 4 and tok_text.startswith(req[:4])):
                                matched.add(req)
                        if len(matched) == len(required):
                            cand_s = seg_tokens[i][1]
                            cand_e = seg_tokens[j][2]
                            width = cand_e - cand_s
                            if best_span is None or width < best_span[0]:
                                best_span = (width, cand_s, cand_e)
                            break
                if best_span is not None:
                    add_hit(best_span[1], best_span[2], "anchored")
                    break

    return hits


def _rebase_span(span: CharSpan | None, offset: int) -> CharSpan | None:
    if span is None:
        return None
    return CharSpan(
        start=span.start + offset,
        end=span.end + offset,
        surface_text=span.surface_text,
        quality=span.quality,
    )


def localize_evidence(
    component_text: str,
    subject_label: str,
    predicate_label: str,
    object_label: str,
    *,
    component_start_in_doc: int,
    component_id: str,
    version_id: str | None = None,
    text_unit_id: str | None = None,
    evidence_hint: str | None = None,
    heading_label: str | None = None,
    allow_inferred_subject: bool = False,
) -> LocalizedSpans | None:
    """Deterministically resolve exact Unicode codepoint spans for (s, p, o) and clause.

    Applies exact -> normalized -> anchored localization with span-width minimization
    tie-breaker `(max_end - min_start, strategy_penalty, min_start, s_start, p_start, o_start)`.
    Returns None when evidence cannot be grounded in `component_text`.
    """
    if not component_text or not component_text.strip() or not object_label.strip():
        return None

    windows = _split_clauses(component_text)
    if not windows:
        return None

    # Prioritize windows overlapping evidence_hint when supplied.
    ordered_windows = list(windows)
    if evidence_hint and evidence_hint.strip():
        hint_hits = _find_role_candidates(
            component_text, (0, len(component_text)), evidence_hint, allow_anchored=False, max_hits=4
        )
        if hint_hits:
            hint_span = hint_hits[0]
            prioritized = [
                w for w in windows if not (w[1] <= hint_span.start or w[0] >= hint_span.end)
            ]
            hint_win = (hint_span.start, hint_span.end)
            if hint_win not in prioritized:
                prioritized.insert(0, hint_win)
            ordered_windows = prioritized + [w for w in windows if w not in prioritized]

    heading_line_end = component_text.find("\n")
    if heading_line_end == -1:
        heading_line_end = len(component_text)
    heading_window = _trim_window(component_text, 0, heading_line_end)

    heading_subject_span: CharSpan | None = None
    if heading_label and heading_window is not None:
        h_hits = _find_role_candidates(
            component_text, heading_window, heading_label, allow_anchored=True, max_hits=2
        )
        if h_hits:
            first = h_hits[0]
            heading_subject_span = CharSpan(
                start=first.start,
                end=first.end,
                surface_text=first.surface_text,
                quality="inferred_from_heading",
            )

    best_key: tuple[int, int, int, int, int, int, int] | None = None
    best_choice: tuple[tuple[int, int], CharSpan | None, CharSpan | None, CharSpan] | None = None

    for win_idx, window in enumerate(ordered_windows):
        obj_hits = _find_role_candidates(
            component_text, window, object_label, allow_anchored=True, max_hits=6
        )
        if not obj_hits:
            continue

        subj_hits = _find_role_candidates(
            component_text, window, subject_label, allow_anchored=True, max_hits=6
        )
        pred_hits = _find_role_candidates(
            component_text, window, predicate_label, allow_anchored=True, max_hits=6
        )

        subj_candidates: list[CharSpan | None]
        if subj_hits:
            subj_candidates = list(subj_hits)
        elif heading_subject_span is not None:
            subj_candidates = [heading_subject_span]
        elif allow_inferred_subject:
            subj_candidates = [None]
        else:
            continue

        pred_candidates: list[CharSpan | None] = list(pred_hits) if pred_hits else [None]

        for s_span in subj_candidates:
            for p_span in pred_candidates:
                for o_span in obj_hits:
                    in_window_spans = [
                        sp
                        for sp in (s_span, p_span, o_span)
                        if sp is not None and sp.quality != "inferred_from_heading"
                    ]
                    min_start = min(sp.start for sp in in_window_spans)
                    max_end = max(sp.end for sp in in_window_spans)
                    span_width = max_end - min_start
                    penalty = sum(
                        _SPAN_QUALITY_PENALTY[sp.quality]
                        for sp in (s_span, p_span, o_span)
                        if sp is not None
                    )
                    if s_span is None:
                        penalty += 2
                    if p_span is None:
                        penalty += 2
                    # Prefer narrower enclosing clause windows slightly when span widths tie.
                    window_width = window[1] - window[0]
                    key = (
                        span_width,
                        penalty,
                        window_width,
                        min_start,
                        s_span.start if s_span is not None else -1,
                        p_span.start if p_span is not None else -1,
                        o_span.start,
                    )
                    if best_key is None or key < best_key:
                        best_key = key
                        best_choice = (window, s_span, p_span, o_span)
        # Stop scanning broader fallback windows once a tight clause match with exact/normalized roles is found.
        if best_choice is not None and win_idx < len(ordered_windows) - 1:
            if best_key is not None and best_key[1] <= 2 and best_choice[0] != (0, len(component_text)):
                break

    if best_choice is None:
        return None

    window, s_span, p_span, o_span = best_choice
    ev_start, ev_end = window
    ev_surface = component_text[ev_start:ev_end]
    ev_quality: SpanMatchQuality = (
        "exact" if o_span.quality == "exact" else ("normalized" if o_span.quality == "normalized" else "clause_window")
    )
    evidence_span = CharSpan(start=ev_start, end=ev_end, surface_text=ev_surface, quality=ev_quality)
    doc_evidence_span = CharSpan(
        start=ev_start + component_start_in_doc,
        end=ev_end + component_start_in_doc,
        surface_text=ev_surface,
        quality=ev_quality,
    )
    return LocalizedSpans(
        component_id=component_id,
        version_id=version_id,
        text_unit_id=text_unit_id,
        evidence_span=evidence_span,
        doc_evidence_span=doc_evidence_span,
        subject_span=_rebase_span(s_span, component_start_in_doc),
        predicate_span=_rebase_span(p_span, component_start_in_doc),
        object_span=_rebase_span(o_span, component_start_in_doc),
        component_start_in_doc=component_start_in_doc,
    )


def format_occurrence_rdf_star(
    token: str,
    doc_id: str,
    subject: RDFTerm,
    predicate: RDFTerm,
    obj: RDFTerm,
    spans: LocalizedSpans,
) -> str:
    """Emit valid RDF-star N-Triples block annotating one grounded statement occurrence."""
    occ_iri = f"<urn:textprov:occ:{token}>"
    quoted = f"<< {subject.ntriples()} {predicate.ntriples()} {obj.ntriples()} >>"
    ev_lit = RDFTerm(
        kind="literal",
        value=spans.doc_evidence_span.surface_text,
        label=spans.doc_evidence_span.surface_text,
        language="es",
    )
    doc_lit = RDFTerm(kind="literal", value=doc_id, label=doc_id)
    unit_lit = RDFTerm(kind="literal", value=spans.component_id, label=spans.component_id)
    tok_lit = RDFTerm(kind="literal", value=token, label=token)
    start_lit = RDFTerm(
        kind="literal",
        value=str(spans.doc_evidence_span.start),
        label=str(spans.doc_evidence_span.start),
        datatype=XSD_INTEGER_IRI,
    )
    end_lit = RDFTerm(
        kind="literal",
        value=str(spans.doc_evidence_span.end),
        label=str(spans.doc_evidence_span.end),
        datatype=XSD_INTEGER_IRI,
    )
    lines = [
        f"{quoted} <{TEXTPROV_NS}occurrenceOf> {occ_iri} .",
        f"{occ_iri} <{RDF_TYPE_IRI}> <{TEXTPROV_NS}StatementOccurrence> .",
        f"{occ_iri} <{TEXTPROV_NS}token> {tok_lit.ntriples()} .",
        f"{occ_iri} <{TEXTPROV_NS}document> {doc_lit.ntriples()} .",
        f"{occ_iri} <{TEXTPROV_NS}sourceUnit> {unit_lit.ntriples()} .",
        f"{occ_iri} <{TEXTPROV_NS}charStart> {start_lit.ntriples()} .",
        f"{occ_iri} <{TEXTPROV_NS}charEnd> {end_lit.ntriples()} .",
        f"{occ_iri} <{TEXTPROV_NS}evidenceText> {ev_lit.ntriples()} .",
    ]
    for role_name, role_span in (
        ("subject", spans.subject_span),
        ("predicate", spans.predicate_span),
        ("object", spans.object_span),
    ):
        if role_span is None:
            continue
        r_start = RDFTerm(
            kind="literal",
            value=str(role_span.start),
            label=str(role_span.start),
            datatype=XSD_INTEGER_IRI,
        )
        r_end = RDFTerm(
            kind="literal",
            value=str(role_span.end),
            label=str(role_span.end),
            datatype=XSD_INTEGER_IRI,
        )
        lines.append(f"{occ_iri} <{TEXTPROV_NS}{role_name}Start> {r_start.ntriples()} .")
        lines.append(f"{occ_iri} <{TEXTPROV_NS}{role_name}End> {r_end.ntriples()} .")
    return "\n".join(lines)


def export_rdf_star_ntriples(graph: GroundedGraph) -> str:
    """Export the full grounded graph as RDF-star N-Triples."""
    header = [
        f"# GraphRAGProv RDF-star N-Triples export for {graph.doc_id} ({graph.revision})",
        f"# Occurrences: {len(graph.occurrences)}",
    ]
    blocks = [occ.rdf_star_nt for occ in graph.occurrences]
    if not blocks:
        return "\n".join(header) + "\n"
    return "\n".join(header) + "\n\n" + "\n\n".join(blocks) + "\n"
