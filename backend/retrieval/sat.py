"""Recuperación SAT: elegibilidad primero, relevancia después.

Adaptaciones experimentales de metadata inheritance, RRF/PPR y recuperación
multigranular. No reproducen íntegramente los sistemas de los papers.
"""

from collections import defaultdict
from datetime import date
from hashlib import sha256
import json
import math
import re
from typing import Literal

from networkx import Graph, pagerank
from ingestion.sat_graph.contracts import SNAPSHOT_STATES

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)
from retrieval.lexical import BM25Index as _BM25Index, legal_terms, terms
from utils.vectors import cosine_scores

class RankStages(BaseModel):
    """Ablación explícita; no altera filtros, presupuestos ni estrategias públicas."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    dense: StrictBool = True
    rerank: StrictBool = True
    ppr_weight: float = Field(
        default=1.0, ge=0.0, le=2.0, allow_inf_nan=False, strict=True
    )


class SearchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    query: str = Field(min_length=1, max_length=4000)
    as_of: date | None = None
    scope: Literal["PE"] = "PE"
    language: Literal["es"] = "es"
    resource_ids: list[str] = Field(default_factory=list, max_length=50)
    component: str | None = Field(default=None, max_length=200)
    strategy: Literal["bm25", "metadata", "hybrid", "ppr", "tree"] = "metadata"
    top_k: int = Field(default=5, ge=1, le=20)
    candidates: int = Field(default=30, ge=1, le=100)
    chunk_chars: int = Field(default=1000, ge=100, le=4000)
    # Presupuesto de bytes UTF-8, no se declara como conteo exacto de tokens.
    context_bytes: int = Field(default=24000, ge=100, le=64000)
    structural_units: bool = False
    include_documentary: bool = False  # opt-in de pruebas; no acredita vigencia histórica

    @field_validator("as_of", mode="before")
    @classmethod
    def explicit_date(cls, value):
        if value is None:
            return None
        if isinstance(value, date) and not hasattr(value, "hour"):
            return value
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Fecha explícita YYYY-MM-DD requerida")
        return value

    @model_validator(mode="after")
    def coherent(self):
        if not self.query.strip():
            raise ValueError("Consulta vacía")
        if self.top_k > self.candidates:
            raise ValueError("top_k supera candidates")
        if self.component is not None and len(self.resource_ids) != 1:
            raise ValueError("Un componente explícito requiere una norma inequívoca")
        return self


def fingerprint(value) -> str:
    return sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def bm25(query: str, texts: dict[str, str]) -> dict[str, float]:
    """Puntúa un conjunto de textos sin reutilizar el índice de un snapshot."""
    return _BM25Index(texts).score(query)


def ranked(scores: dict[str, float]) -> list[str]:
    return sorted(scores, key=lambda identity: (-scores[identity], identity))


def rrf(rankings: list[list[str]], k: int = 60, weights=None) -> dict[str, float]:
    scores = defaultdict(float)
    weights = [1.0] * len(rankings) if weights is None else weights
    if len(weights) != len(rankings):
        raise ValueError("Cada ranking requiere un peso")
    for ranking, weight in zip(rankings, weights, strict=True):
        if not math.isfinite(weight) or weight < 0:
            raise ValueError("Peso RRF inválido")
        if weight == 0:
            continue
        for position, identity in enumerate(dict.fromkeys(ranking), 1):
            scores[identity] += weight / (k + position)
    return dict(scores)


def eligible_version_ids(
    nodes: dict[str, dict],
    outgoing: dict[tuple[str, str], list[str]],
    *,
    scope: str = "PE",
    language: str = "es",
) -> set[str]:
    """Read-only eligibility check matching ``SATRetriever.eligible(SearchPlan(query='corpus'))``."""
    groups = defaultdict(list)
    for node in nodes.values():
        if node.get("editorial_superseded_by"):
            continue
        if (
            node["type"] == "CTV"
            and node.get("provenance_state") in SNAPSHOT_STATES | {"reviewed"}
            and node["scope"] == scope
        ):
            groups[node["work_id"]].append(node)
    eligible: set[str] = set()
    for wid, versions in groups.items():
        if len(versions) > 1:
            keys = [v.get("snapshot_as_of") or v.get("valid_from") or "" for v in versions]
            newest = max(keys)
            versions = [v for v, key in zip(versions, keys) if key == newest] if newest else []
        if len(versions) != 1:
            continue
        version = versions[0]
        if version.get("valid_to") is not None:
            continue
        work = nodes[wid]
        if (
            version.get("provenance_state") in SNAPSHOT_STATES
            and work.get("kind") not in {"article", "numeral", "inciso", "subinciso", "disposition"}
        ):
            continue
        texts = [
            nodes[target]
            for target in outgoing.get((version["id"], "has_text"), ())
            if nodes[target].get("language") == language
        ]
        if len(texts) != 1:
            continue
        eligible.add(version["id"])
    return eligible


class SATRetriever:
    """Snapshot inmutable por consulta; ninguna búsqueda lee candidatos sin revisar."""

    def __init__(self, snapshot: dict):
        # Desacoplar el fingerprint y la lectura de mutaciones externas posteriores.
        from copy import deepcopy

        snapshot = deepcopy(snapshot)
        self.snapshot = snapshot
        self.revision = fingerprint(snapshot)
        self.nodes = {node["id"]: node for node in snapshot["nodes"]}
        self.edges = snapshot["edges"]
        # Per immutable snapshot only: never reuse eligibility across revisions.
        self._eligible_cache = {}
        self._rank_cache = None
        from threading import RLock
        self._rank_cache_lock = RLock()
        self.outgoing = defaultdict(list)
        self.incoming_contains = defaultdict(list)
        for edge in self.edges:
            self.outgoing[(edge["source"], edge["type"])].append(edge["target"])
            if edge["type"] == "contains_version":
                self.incoming_contains[edge["target"]].append(edge["source"])

    def _texts(self, version, language):
        return [
            self.nodes[target]
            for target in self.outgoing[(version["id"], "has_text")]
            if self.nodes[target].get("language") == language
        ]

    def _ancestor_headings(self, version_id: str, language: str) -> str:
        """Collect structural parent labels and short container headings via contains_version."""
        parts: list[str] = []
        seen = {version_id}
        frontier = list(self.incoming_contains.get(version_id, ()))
        depth = 0
        while frontier and depth < 8:
            next_frontier: list[str] = []
            for parent_id in frontier:
                if parent_id in seen:
                    continue
                seen.add(parent_id)
                parent_ctv = self.nodes.get(parent_id)
                if not parent_ctv or parent_ctv.get("type") != "CTV":
                    continue
                work = self.nodes.get(parent_ctv.get("work_id"))
                if work:
                    label = (work.get("label") or "").strip()
                    if label:
                        parts.append(label)
                    if work.get("kind") not in {"article", "numeral", "inciso", "subinciso"}:
                        texts = self._texts(parent_ctv, language)
                        if len(texts) == 1:
                            lines = [
                                line.lstrip("#").strip()
                                for line in (texts[0].get("text") or "").splitlines()[:3]
                                if line.strip()
                            ]
                            snippet = " ".join(lines)[:200].strip()
                            if snippet and snippet != label:
                                parts.append(snippet)
                next_frontier.extend(self.incoming_contains.get(parent_id, ()))
            frontier = next_frontier
            depth += 1
        return " ".join(dict.fromkeys(parts))

    def eligible(self, plan: SearchPlan) -> list[dict]:
        cache_key = (plan.as_of, plan.scope, plan.language, tuple(plan.resource_ids), plan.component)
        cached = self._eligible_cache.get(cache_key)
        if cached is not None:
            return list(cached)
        when = plan.as_of.isoformat() if plan.as_of else None
        groups = defaultdict(list)
        for node in self.nodes.values():
            if node.get("editorial_superseded_by"):
                continue
            if when is None and node["type"] == "CTV" and node.get("provenance_state") in SNAPSHOT_STATES | {"reviewed"}:
                if node["scope"] == plan.scope:
                    groups[node["work_id"]].append(node)
            elif node["type"] == "CTV" and node.get("provenance_state") == "user_attested_snapshot":
                if node["scope"] == plan.scope and node.get("snapshot_as_of") == when:
                    groups[node["work_id"]].append(node)
            elif node["type"] == "CTV" and node.get("provenance_state") == "reviewed":
                if (
                    node["scope"] == plan.scope
                    and node["valid_from"] <= when
                    and (node["valid_to"] is None or when < node["valid_to"])
                ):
                    groups[node["work_id"]].append(node)
        result = []
        for wid, versions in groups.items():
            if when is None and len(versions) > 1:
                # La fecha ordena versiones almacenadas; no verifica vigencia externa.
                keys = [v.get("snapshot_as_of") or v.get("valid_from") or "" for v in versions]
                newest = max(keys)
                versions = [v for v, key in zip(versions, keys) if key == newest] if newest else []
            # Un conflicto de versiones no se resuelve por score semántico.
            if len(versions) != 1:
                continue
            version = versions[0]
            # Una versión cerrada explícitamente en el grafo no vuelve a activarse.
            if when is None and version.get("valid_to") is not None:
                continue
            work = self.nodes[wid]
            if version.get("provenance_state") in SNAPSHOT_STATES and work.get("kind") not in {"article", "numeral", "inciso", "subinciso", "disposition"}:
                continue
            if when is not None and when > version["checked_through"]:
                continue
            if plan.resource_ids and work["resource_id"] not in plan.resource_ids:
                continue
            if plan.component is not None and work["component"] != plan.component:
                continue
            texts = self._texts(version, plan.language)
            if len(texts) != 1:
                continue
            result.append({"version": version, "work": work, "text": texts[0]})
        result = sorted(result, key=lambda item: item["version"]["id"])
        self._eligible_cache[cache_key] = tuple(result)
        return list(result)

    def chunks(self, plan: SearchPlan) -> list[dict]:
        result = []
        for item in self.eligible(plan):
            version, work, text = item["version"], item["work"], item["text"]
            # La publicación modificatoria anterior se conserva para citas
            # explícitas; no es evidencia para preguntas sobre la regla actual.
            if plan.as_of is None and version.get("historical_quotation"):
                continue
            body = text["text"]
            resource = self.nodes[work["resource_id"]]
            # Sin overlap: la evidencia canónica no se duplica ni se altera.
            step = max(len(body), 1) if plan.structural_units else plan.chunk_chars
            for start in range(0, len(body), step):
                end = min(len(body), start + step)
                content = body[start:end]
                result.append(
                    {
                        "id": "tu:"
                        + fingerprint([version["id"], text["id"], start, end]),
                        "version_id": version["id"],
                        "text_id": text["id"],
                        "work_id": work["id"],
                        "resource_id": work["resource_id"],
                        "component": work["component"],
                        "label": work["label"],
                        "resource_label": resource.get("title", work["resource_id"]),
                        "content": content,
                        "start": text["start"] + start,
                        "end": text["start"] + end,
                        "text_sha256": sha256(content.encode()).hexdigest(),
                        "evidence_id": text["evidence_id"],
                        "source_url": text["source_url"],
                        "review_id": version["review_id"],
                        "as_of": plan.as_of.isoformat() if plan.as_of else None,
                        "valid_from": version["valid_from"],
                        "valid_to": version["valid_to"],
                        "checked_through": version["checked_through"],
                        "language": plan.language,
                        "scope": plan.scope,
                        "provenance_state": version["provenance_state"],
                        "snapshot_as_of": version.get("snapshot_as_of"),
                        "amending_source": version.get("amending_source"),
                        "text_review_state": version.get("text_review_state"),
                    }
                )
        if getattr(plan, "include_documentary", False):
            result.extend(self._documentary_chunks(plan))
        return result

    def _documentary_chunks(self, plan):
        """Versiones documentales aprobadas: recuperación experimental, no CTV."""
        mapping = {
            "ley-30364-original": "pe:ley:30364", "ley-28970": "pe:ley:28970",
            "ley-30490": "pe:ley:30490", "ley-31464": "pe:ley:31464",
            "ds-004-2025-mimp": "pe:ds:004-2025-mimp",
            "ds-005-2022-mimp": "pe:ds:005-2022-mimp",
            "ds-024-2021-mimp": "pe:ds:024-2021-mimp",
            "rm-100-2021-mimp": "pe:rm:100-2021-mimp",
        }
        revisions = defaultdict(list)
        for n in self.nodes.values():
            if n["type"] == "DocumentaryRevision" and not n.get("editorial_superseded_by"):
                revisions[n["directory"]].append(n)
        selected = {items[0]["id"]: items[0] for items in revisions.values() if len(items) == 1}
        result = []
        for node in self.nodes.values():
            if node["type"] != "DocumentaryComponent" or node["revision_id"] not in selected:
                continue
            if node["kind"] not in {"article", "numeral", "inciso", "subinciso", "disposition"}:
                continue
            rev = selected[node["revision_id"]]
            resource_id = mapping.get(rev["directory"])
            if resource_id not in self.nodes or (plan.resource_ids and resource_id not in plan.resource_ids):
                continue
            if plan.component is not None and plan.component != node["source_node_id"]:
                continue
            body = rev["markdown"][node["start"]:node["end"]]
            if sha256(body.encode()).hexdigest() != node["text_sha256"]:
                raise ValueError("Fragmento documental alterado")
            resource = self.nodes[resource_id]
            for offset in range(0, len(body), plan.chunk_chars):
                content = body[offset:offset + plan.chunk_chars]
                result.append({
                    "id": "tu-doc:" + fingerprint([node["id"], offset, content]),
                    "version_id": node["id"], "text_id": rev["id"], "work_id": node["id"],
                    "resource_id": resource_id, "component": node["source_node_id"],
                    "label": node["label"], "resource_label": resource.get("title", resource_id),
                    "content": content, "start": node["start"] + offset,
                    "end": node["start"] + offset + len(content),
                    "text_sha256": sha256(content.encode()).hexdigest(),
                    "evidence_id": rev["evidence_id"], "source_url": resource.get("url"),
                    "review_id": rev["review_hash"], "as_of": None,
                    "valid_from": None, "valid_to": None, "checked_through": None,
                    "language": "es", "scope": "PE", "provenance_state": "assumed_current_documentary",
                    "text_review_state": rev.get("text_review_state"),
                })
        return result

    def _ppr(self, chunks, seeds, *, use_memberships=True):
        """PPR sobre membresías de versiones elegibles; no grafo LLM inferido."""
        ids = {chunk["version_id"] for chunk in chunks}
        seed_chunks = set(seeds)
        seed_ids = {chunk["version_id"] for chunk in chunks if chunk["id"] in seed_chunks}
        if not seed_ids:
            return {}
        graph = Graph()
        graph.add_nodes_from(sorted(ids))
        if use_memberships:
            graph.add_edges_from(
                (edge["source"], edge["target"]) for edge in self.edges
                if edge["type"] == "contains_version"
                and edge["source"] in ids and edge["target"] in ids
            )
        personal = dict.fromkeys(seed_ids, 1.0)
        # NetworkX uses len(graph) * tol for total L1 error. Allow convergence
        # instead of accepting the last iterate unconditionally after 50 steps.
        scores = pagerank(
            graph, alpha=0.85, personalization=personal, nstart=personal,
            dangling=personal, weight=None, tol=1e-10 / len(graph), max_iter=200,
        )
        return {
            chunk["id"]: scores[chunk["version_id"]]
            for chunk in chunks
            if scores[chunk["version_id"]] > 0
        }

    def search(
        self, plan: SearchPlan, *, provider=None, stages: RankStages | None = None
    ) -> dict:
        stages = stages or RankStages()
        # One cached index per immutable snapshot; changing any field that
        # affects eligibility/chunking rebuilds it. Never cache user queries.
        cache_key = plan.model_dump_json(exclude={'query', 'top_k', 'candidates', 'strategy', 'context_bytes'})
        with self._rank_cache_lock:
            if self._rank_cache is None or self._rank_cache[0] != cache_key:
                chunks = self.chunks(plan)
                raw_index = _BM25Index({c['id']: c['content'] for c in chunks}, tokenize=legal_terms)
                metadata_index = _BM25Index(
                    {
                        c['id']: (
                            f'{c["resource_label"]} '
                            f'{self._ancestor_headings(c["version_id"], plan.language)} '
                            f'{c["label"]} {c["component"]} {c["content"]}'
                        )
                        for c in chunks
                    },
                    tokenize=legal_terms,
                )
                self._rank_cache = (cache_key, chunks, raw_index, metadata_index)
            _, chunks, raw_index, metadata_index = self._rank_cache
        by_id = {chunk["id"]: chunk for chunk in chunks}
        raw = raw_index.score(plan.query)
        metadata = metadata_index.score(plan.query)
        rankings = [ranked(raw)]
        weights = [1.0]
        if plan.strategy != "bm25":
            rankings.append(ranked(metadata))
            weights.append(1.0)
        api = {"requests": 0, "tokens": 0, "cache_hits": 0}
        api_stages = {stage: dict(api) for stage in ("dense", "rerank")}
        dense_status = rerank_status = "not_run"
        if (
            provider is not None
            and stages.dense
            and plan.strategy in {"hybrid", "ppr", "tree"}
            and chunks
        ):
            # Nunca mezclar instrumentos/versiones en un grupo contextual.
            grouped = defaultdict(list)
            for chunk in chunks:
                grouped[(chunk["resource_id"], chunk["version_id"])].append(chunk)
            groups = [
                sorted(grouped[key], key=lambda c: c["start"])
                for key in sorted(grouped)
            ]
            vectors, usage = provider.embed(
                [[c["content"] for c in group] for group in groups]
            )
            query_vectors, query_usage = provider.embed(
                [[plan.query]], input_type="query"
            )
            aligned = [
                (chunk["id"], vector)
                for group, embedded in zip(groups, vectors, strict=True)
                for chunk, vector in zip(group, embedded, strict=True)
            ]
            ids, rows = zip(*aligned, strict=True)
            dense = dict(zip(ids, cosine_scores(rows, query_vectors[0][0]), strict=True))
            rankings.append(ranked(dense))
            weights.append(1.0)
            dense_status = "executed"
            for key in api:
                api[key] += usage[key] + query_usage[key]
                api_stages["dense"][key] += usage[key] + query_usage[key]
        ppr_status = None
        if plan.strategy == "ppr":
            seeds = ranked(metadata)[:5]
            use_memberships = (
                getattr(plan, "membership_policy", "verified") == "verified"
            )
            ppr_scores = self._ppr(chunks, seeds, use_memberships=use_memberships)
            rankings.append(ranked(ppr_scores))
            weights.append(stages.ppr_weight)
            eligible_versions = {c["version_id"] for c in chunks}
            seed_versions = {by_id[i]["version_id"] for i in seeds}
            scored_versions = {by_id[i]["version_id"] for i in ppr_scores}
            ppr_status = {
                "solver": "networkx_pagerank",
                "membership_policy": "verified" if use_memberships else "disabled",
                "weight": stages.ppr_weight,
                "eligible_membership_edges": sum(
                    e["type"] == "contains_version"
                    and e["source"] in eligible_versions
                    and e["target"] in eligible_versions
                    for e in self.edges
                ),
                "seed_versions": len(seed_versions),
                "scored_versions": len(scored_versions),
                "expanded_versions": len(scored_versions - seed_versions),
            }
            ppr_status["used_membership_edges"] = (
                ppr_status["eligible_membership_edges"]
                if use_memberships and stages.ppr_weight > 0
                else 0
            )
        if plan.strategy == "tree":
            # Adaptación extractiva multigranular, NO índice Psi-RAG completo.
            overviews = defaultdict(list)
            for chunk in chunks:
                overviews[chunk["resource_id"]].append(
                    f'{chunk["label"]} {chunk["content"]}'
                )
            parent_rank = ranked(
                bm25(
                    plan.query,
                    {key: "\n".join(value) for key, value in overviews.items()},
                )
            )
            child_rank = ranked(metadata)
            rankings.append(
                [
                    identity
                    for resource in parent_rank
                    for identity in child_rank
                    if by_id[identity]["resource_id"] == resource
                ]
            )
            weights.append(1.0)
        scores = rrf(rankings, weights=weights)
        ordered = ranked(scores)[: plan.candidates]
        if (
            provider is not None
            and stages.rerank
            and ordered
            and plan.strategy in {"hybrid", "ppr", "tree"}
        ):
            # Orden canónico: mismos candidatos de otra ablación reutilizan el rerank.
            rerank_ids = sorted(ordered)
            reordered, usage = provider.rerank(
                plan.query,
                [by_id[i]["content"] for i in rerank_ids],
                top_k=len(rerank_ids),
            )
            ordered = [rerank_ids[index] for index, _ in reordered]
            rerank_status = "executed"
            for key in api:
                api[key] += usage[key]
                api_stages["rerank"][key] += usage[key]
        hits, used = [], 0
        seen_versions = set()
        # Evaluación y contexto a nivel CTV: no inflar resultados con subchunks.
        for identity in ordered:
            chunk = by_id[identity]
            if chunk["version_id"] in seen_versions:
                continue
            size = len(chunk["content"].encode("utf-8"))
            if used + size > plan.context_bytes:
                if plan.structural_units and not hits:
                    break
                continue
            hits.append({**chunk, "score": scores[identity]})
            seen_versions.add(chunk["version_id"])
            used += size
            if len(hits) == plan.top_k:
                break
        return {
            "state": "retrieved" if hits else "abstain",
            "engine": "sat",
            "reason": None if hits else "no_eligible_relevant_evidence_within_budget",
            "revision": self.revision,
            "strategy": plan.strategy,
            "as_of": str(plan.as_of) if plan.as_of else None,
            "eligible_chunks": len(chunks),
            "candidate_count": len(ordered),
            "context_bytes": used,
            "api": api,
            "api_stages": api_stages,
            "hits": hits,
            "dense_status": dense_status,
            "rerank_status": rerank_status,
            "ppr_status": ppr_status,
        }

    def history(self, resource_id: str, component: str) -> dict:
        from ingestion.sat_graph.store import work_id

        wid = work_id(resource_id, component)
        versions = sorted(
            [
                n
                for n in self.nodes.values()
                if n["type"] == "CTV" and n["work_id"] == wid
            ],
            key=lambda n: (n.get("valid_from") or n.get("snapshot_as_of") or "", n["id"]),
        )
        ids = {version["id"] for version in versions}
        action_ids = {
            e["source"]
            for e in self.edges
            if e["type"] in {"terminates", "produces"} and e["target"] in ids
        }
        actions = sorted(
            [self.nodes[aid] for aid in action_ids],
            key=lambda n: (n["effective_on"], n["id"]),
        )
        return {
            "state": "resolved" if versions else "abstain",
            "work_id": wid,
            "revision": self.revision,
            "versions": versions,
            "actions": actions,
            "causal_edges": [
                e
                for e in self.edges
                if e["source"] in action_ids
                and e["type"] in {"terminates", "produces", "source"}
            ],
            "policy": ("reviewed_history_and_attested_snapshots_not_current_applicability" if any(v.get("provenance_state") in SNAPSHOT_STATES for v in versions) else "all_reviewed_history_not_current_applicability"),
        }
