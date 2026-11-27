"""Cached workspace service assembling grounded provenance graphs and query traces."""
from __future__ import annotations

import asyncio
from collections import OrderedDict, defaultdict
from hashlib import sha256
from threading import RLock
from typing import Any, Literal, Sequence

from services.graphragprov.extractor import (
    CohereGroundedExtractor,
    DeterministicLegalExtractor,
)
from services.graphragprov.localizer import export_rdf_star_ntriples
from services.graphragprov.models import (
    EvalLimits,
    GroundedGraph,
    RDFTerm,
    StatementOccurrence,
)
from services.graphragprov.nl_sparql import (
    compile_nl_to_sparql_cohere,
    compile_nl_to_sparql_deterministic,
)
from services.graphragprov.semiring import (
    expand_to_polynomial,
    parse_npcs_prefix,
)
from services.graphragprov.sparql import evaluate_sparql

ExtractionMode = Literal["deterministic", "hybrid_cohere"]
NLMode = Literal["deterministic", "cohere"]


def _node_id_for_term(term: RDFTerm) -> str:
    if term.kind == "iri":
        return f"iri:{term.value}"
    if term.kind == "bnode":
        return f"bnode:{term.value}"
    digest = sha256(term.ntriples().encode("utf-8")).hexdigest()[:12]
    return f"lit:{digest}"


def build_subgraph(occurrences: Sequence[StatementOccurrence]) -> dict[str, Any]:
    """Build node/edge SVG subgraph DTO with deterministic parallel_index for curved edges."""
    nodes_by_id: dict[str, dict[str, Any]] = {}
    pair_groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    raw_edges: list[dict[str, Any]] = []

    for occ in occurrences:
        src_id = _node_id_for_term(occ.subject)
        dst_id = _node_id_for_term(occ.object)
        if src_id not in nodes_by_id:
            nodes_by_id[src_id] = {
                "id": src_id,
                "label": occ.subject.label,
                "kind": occ.subject.kind,
                "value": occ.subject.value,
            }
        if dst_id not in nodes_by_id:
            nodes_by_id[dst_id] = {
                "id": dst_id,
                "label": occ.object.label,
                "kind": occ.object.kind,
                "value": occ.object.value,
            }
        edge_idx = len(raw_edges)
        pair_key = (min(src_id, dst_id), max(src_id, dst_id))
        pair_groups[pair_key].append(edge_idx)
        raw_edges.append(
            {
                "token": occ.token,
                "source": src_id,
                "target": dst_id,
                "predicate": occ.predicate.label,
                "predicate_iri": occ.predicate.value,
                "origin": occ.origin,
                "component_id": occ.spans.component_id,
                "parallel_index": 0,
                "parallel_count": 1,
            }
        )

    for indices in pair_groups.values():
        count = len(indices)
        for pos, edge_idx in enumerate(indices):
            raw_edges[edge_idx]["parallel_index"] = pos
            raw_edges[edge_idx]["parallel_count"] = count

    return {
        "nodes": list(nodes_by_id.values()),
        "edges": raw_edges,
    }


def serialize_graph(graph: GroundedGraph) -> dict[str, Any]:
    """Serialize a GroundedGraph into a self-contained JSON-safe DTO."""
    return {
        "doc_id": graph.doc_id,
        "revision": graph.revision,
        "source_kind": graph.source_kind,
        "markdown_sha256": graph.markdown_sha256,
        "namespaces": dict(graph.namespaces),
        "occurrences": [occ.to_dict() for occ in graph.occurrences],
        "predicates": list(graph.predicates),
        "cohere_used": graph.cohere_used,
        "unlocalized_discarded": graph.unlocalized_discarded,
        "sample_queries": [sq.to_dict() for sq in graph.sample_queries],
        "source_units": {uid: unit.to_dict() for uid, unit in graph.source_units.items()},
        "subgraph": build_subgraph(graph.occurrences),
        "stats": {
            "units": len(graph.source_units),
            "occurrences": len(graph.occurrences),
            "predicates": len(graph.predicates),
            "unlocalized_discarded": graph.unlocalized_discarded,
        },
    }


def parse_polynomial_expression(raw: str, *, max_terms: int = 512) -> dict[str, Any]:
    """Parse an NPCS or SparqlProv provenance expression and return expanded forms."""
    expr = parse_npcs_prefix(raw)
    poly = expand_to_polynomial(expr, max_terms=max_terms)
    return {
        "npcs_prefix": poly.npcs_prefix,
        "infix": poly.infix_display,
        "compact_infix": poly.compact_infix,
        "monomials": [m.to_dict() for m in poly.monomials],
        "witness_tokens": list(poly.witness_tokens),
        "total_multiplicity": poly.total_multiplicity,
        "truncated": poly.truncated,
    }


def _cache_key(
    doc_payload: dict[str, Any],
    *,
    mode: ExtractionMode,
    component_ids: Sequence[str] | None,
    edition_override: dict[str, Any] | None,
) -> tuple[str, str, str, str, str]:
    doc_id = str(doc_payload.get("id") or "unknown")
    edition = edition_override if edition_override is not None else doc_payload.get("edition")
    revision = str((edition or {}).get("revision") or (doc_payload.get("revisions") or ["snapshot"])[0])
    if edition and edition.get("markdown"):
        md_sha = sha256(str(edition["markdown"]).encode("utf-8")).hexdigest()
    else:
        pieces = []
        for ver in doc_payload.get("versions") or ():
            if ver.get("archived"):
                continue
            texts = ver.get("texts") or ()
            if texts:
                pieces.append(f"{ver.get('id')}:{texts[0].get('text', '')}")
        md_sha = sha256("\n".join(pieces).encode("utf-8")).hexdigest()
    scope_key = ",".join(sorted(set(component_ids))) if component_ids else "*"
    return (doc_id, revision, md_sha, scope_key, mode)


class ProvenanceWorkspaceService:
    """Thread-safe LRU-cached read-side projection service for GraphRAGProv."""

    def __init__(self, *, max_cache_entries: int = 16) -> None:
        self._lock = RLock()
        self._cache: OrderedDict[tuple[str, str, str, str, str], GroundedGraph] = OrderedDict()
        self._max_cache_entries = max(1, max_cache_entries)
        self._deterministic = DeterministicLegalExtractor()

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    def _cache_get(self, key: tuple[str, str, str, str, str]) -> GroundedGraph | None:
        with self._lock:
            found = self._cache.get(key)
            if found is not None:
                self._cache.move_to_end(key)
            return found

    def _cache_put(self, key: tuple[str, str, str, str, str], graph: GroundedGraph) -> None:
        with self._lock:
            self._cache[key] = graph
            self._cache.move_to_end(key)
            while len(self._cache) > self._max_cache_entries:
                self._cache.popitem(last=False)

    def get_or_build_deterministic(
        self,
        doc_payload: dict[str, Any],
        *,
        component_ids: Sequence[str] | None = None,
        edition_override: dict[str, Any] | None = None,
    ) -> GroundedGraph:
        key = _cache_key(
            doc_payload,
            mode="deterministic",
            component_ids=component_ids,
            edition_override=edition_override,
        )
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        graph = self._deterministic.extract(
            doc_payload,
            edition_override=edition_override,
            component_ids=component_ids,
        )
        self._cache_put(key, graph)
        return graph

    async def get_or_build_graph(
        self,
        doc_payload: dict[str, Any],
        *,
        mode: ExtractionMode = "deterministic",
        component_ids: Sequence[str] | None = None,
        edition_override: dict[str, Any] | None = None,
        cohere_api_key: str | None = None,
        cohere_model: str = "command-r7b-12-2024",
    ) -> GroundedGraph:
        if mode == "deterministic":
            return await asyncio.to_thread(
                self.get_or_build_deterministic,
                doc_payload,
                component_ids=component_ids,
                edition_override=edition_override,
            )
        if not cohere_api_key:
            raise ValueError(
                "COHERE_API_KEY no está configurada; utilice el modo determinístico sin conexión."
            )
        key = _cache_key(
            doc_payload,
            mode="hybrid_cohere",
            component_ids=component_ids,
            edition_override=edition_override,
        )
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        base = await asyncio.to_thread(
            self.get_or_build_deterministic,
            doc_payload,
            component_ids=component_ids,
            edition_override=edition_override,
        )
        extractor = CohereGroundedExtractor(api_key=cohere_api_key, model=cohere_model)
        merged = await extractor.extract(doc_payload, base_graph=base)
        self._cache_put(key, merged)
        return merged

    def export_ntriples(self, graph: GroundedGraph) -> str:
        return export_rdf_star_ntriples(graph)

    async def run_query(
        self,
        graph: GroundedGraph,
        *,
        question: str | None = None,
        sparql: str | None = None,
        nl_mode: NLMode = "deterministic",
        max_rows: int = 100,
        cohere_api_key: str | None = None,
        cohere_model: str = "command-r7b-12-2024",
    ) -> dict[str, Any]:
        warnings: list[str] = []
        nl_compiler: Literal["none", "deterministic_template", "cohere_llm"] = "none"
        effective_sparql = (sparql or "").strip()

        if not effective_sparql:
            if not question or not question.strip():
                raise ValueError("Proporcione una pregunta en lenguaje natural o una consulta SPARQL SELECT")
            if nl_mode == "cohere":
                if not cohere_api_key:
                    raise ValueError(
                        "COHERE_API_KEY no está configurada; utilice nl_mode='deterministic'."
                    )
                effective_sparql, nl_warnings = await compile_nl_to_sparql_cohere(
                    question,
                    graph,
                    api_key=cohere_api_key,
                    model=cohere_model,
                )
                nl_compiler = "cohere_llm"
            else:
                effective_sparql, nl_warnings = compile_nl_to_sparql_deterministic(question, graph)
                nl_compiler = "deterministic_template"
            warnings.extend(nl_warnings)

        limits = EvalLimits(max_rows=max_rows)
        eval_result = evaluate_sparql(graph, effective_sparql, limits=limits)
        warnings.extend(eval_result.warnings)

        serialized_rows: list[dict[str, Any]] = []
        for idx, row in enumerate(eval_result.rows):
            poly = row.polynomial
            serialized_rows.append(
                {
                    "row_index": idx,
                    "bindings": {
                        var: (term.to_dict() if term is not None else None)
                        for var, term in row.bindings.items()
                    },
                    "polynomial": poly.infix_display,
                    "compact_polynomial": poly.compact_infix,
                    "npcs_prefix": poly.npcs_prefix,
                    "monomials": [m.to_dict() for m in poly.monomials],
                    "witness_count": poly.total_multiplicity,
                    "occurrence_tokens": list(poly.witness_tokens),
                    "truncated": poly.truncated,
                }
            )

        referenced_occs: list[StatementOccurrence] = []
        occ_map: dict[str, dict[str, Any]] = {}
        referenced_unit_ids: set[str] = set()
        for tok in eval_result.referenced_tokens:
            pos = graph.by_token.get(tok)
            if pos is None:
                continue
            occ = graph.occurrences[pos]
            referenced_occs.append(occ)
            occ_map[tok] = occ.to_dict()
            referenced_unit_ids.add(occ.spans.component_id)

        if referenced_unit_ids:
            units_dto = {
                uid: graph.source_units[uid].to_dict()
                for uid in sorted(referenced_unit_ids)
                if uid in graph.source_units
            }
        else:
            units_dto = {uid: unit.to_dict() for uid, unit in graph.source_units.items()}

        return {
            "doc_id": graph.doc_id,
            "revision": graph.revision,
            "question": question,
            "sparql": effective_sparql,
            "nl_compiler": nl_compiler,
            "variables": list(eval_result.variables),
            "rows": serialized_rows,
            "occurrences": occ_map,
            "source_units": units_dto,
            "subgraph": build_subgraph(referenced_occs),
            "execution_ms": eval_result.elapsed_ms,
            "warnings": warnings,
        }
