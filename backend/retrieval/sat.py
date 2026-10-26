"""Recuperación SAT: elegibilidad primero, relevancia después.

Adaptaciones experimentales de metadata inheritance, RRF/PPR y recuperación
multigranular. No reproducen íntegramente los sistemas de los papers.
"""

from collections import Counter, defaultdict
from datetime import date
from hashlib import sha256
import json
import math
import re
import unicodedata
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)


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
    as_of: date
    scope: Literal["PE"] = "PE"
    language: Literal["es"] = "es"
    resource_ids: list[str] = Field(default_factory=list, max_length=50)
    component: str | None = Field(default=None, max_length=200)
    strategy: Literal["bm25", "metadata", "hybrid", "ppr", "tree"] = "metadata"
    top_k: int = Field(default=5, ge=1, le=20)
    candidates: int = Field(default=30, ge=1, le=100)
    chunk_chars: int = Field(default=1000, ge=100, le=4000)
    # Presupuesto de bytes UTF-8, no se declara como conteo exacto de tokens.
    context_bytes: int = Field(default=16000, ge=100, le=64000)

    @field_validator("as_of", mode="before")
    @classmethod
    def explicit_date(cls, value):
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


def terms(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", normalized)


def bm25(query: str, texts: dict[str, str]) -> dict[str, float]:
    """BM25 Okapi con desempate posterior por ID; sin etiquetas gold."""
    counts = {identity: Counter(terms(text)) for identity, text in texts.items()}
    if not counts:
        return {}
    lengths = {identity: sum(counter.values()) for identity, counter in counts.items()}
    avg = sum(lengths.values()) / len(lengths) or 1
    df = Counter(term for counter in counts.values() for term in counter)
    scores = {}
    for identity, counter in counts.items():
        score = 0.0
        for term in set(terms(query)):
            freq = counter[term]
            if freq:
                idf = math.log(1 + (len(counts) - df[term] + 0.5) / (df[term] + 0.5))
                score += (
                    idf
                    * freq
                    * 2.2
                    / (freq + 1.2 * (0.25 + 0.75 * lengths[identity] / avg))
                )
        if score > 0:
            scores[identity] = score
    return scores


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


def cosine(left, right):
    if len(left) != len(right) or not left:
        raise ValueError("Dimensiones incompatibles")
    if not all(math.isfinite(x) for x in [*left, *right]):
        raise ValueError("Vector no finito")
    norm = math.sqrt(sum(x * x for x in left) * sum(x * x for x in right))
    return sum(a * b for a, b in zip(left, right)) / norm if norm else 0.0


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
        self.outgoing = defaultdict(list)
        for edge in self.edges:
            self.outgoing[(edge["source"], edge["type"])].append(edge["target"])

    def _texts(self, version, language):
        return [
            self.nodes[target]
            for target in self.outgoing[(version["id"], "has_text")]
            if self.nodes[target].get("language") == language
        ]

    def eligible(self, plan: SearchPlan) -> list[dict]:
        when = plan.as_of.isoformat()
        groups = defaultdict(list)
        for node in self.nodes.values():
            if node["type"] == "CTV" and node.get("provenance_state") == "reviewed":
                if (
                    node["scope"] == plan.scope
                    and node["valid_from"] <= when
                    and (node["valid_to"] is None or when < node["valid_to"])
                ):
                    groups[node["work_id"]].append(node)
        result = []
        for wid, versions in groups.items():
            # Un conflicto de versiones no se resuelve por score semántico.
            if len(versions) != 1:
                continue
            version = versions[0]
            work = self.nodes[wid]
            if when > version["checked_through"]:
                continue
            if plan.resource_ids and work["resource_id"] not in plan.resource_ids:
                continue
            if plan.component is not None and work["component"] != plan.component:
                continue
            texts = self._texts(version, plan.language)
            if len(texts) != 1:
                continue
            result.append({"version": version, "work": work, "text": texts[0]})
        return sorted(result, key=lambda item: item["version"]["id"])

    def chunks(self, plan: SearchPlan) -> list[dict]:
        result = []
        for item in self.eligible(plan):
            version, work, text = item["version"], item["work"], item["text"]
            body = text["text"]
            resource = self.nodes[work["resource_id"]]
            # Sin overlap: la evidencia canónica no se duplica ni se altera.
            for start in range(0, len(body), plan.chunk_chars):
                end = min(len(body), start + plan.chunk_chars)
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
                        "as_of": plan.as_of.isoformat(),
                        "valid_from": version["valid_from"],
                        "valid_to": version["valid_to"],
                        "checked_through": version["checked_through"],
                        "language": plan.language,
                        "scope": plan.scope,
                        "provenance_state": "reviewed",
                    }
                )
        return result

    def _ppr(self, chunks, seeds, *, use_memberships=True):
        """PPR sobre membresías de versiones elegibles; no grafo LLM inferido."""
        ids = {chunk["version_id"] for chunk in chunks}
        adjacency = {identity: set() for identity in ids}
        for edge in self.edges:
            if (
                edge["type"] == "contains_version"
                and use_memberships
                and edge["source"] in ids
                and edge["target"] in ids
            ):
                adjacency[edge["source"]].add(edge["target"])
                adjacency[edge["target"]].add(edge["source"])
        seed_ids = {chunk["version_id"] for chunk in chunks if chunk["id"] in seeds}
        if not seed_ids:
            return {}
        personal = {
            identity: (1 / len(seed_ids) if identity in seed_ids else 0)
            for identity in ids
        }
        scores = dict(personal)
        for _ in range(50):
            dangling = sum(scores[v] for v in ids if not adjacency[v])
            updated = {v: (0.15 + 0.85 * dangling) * personal[v] for v in ids}
            for source in sorted(ids):
                if adjacency[source]:
                    for target in sorted(adjacency[source]):
                        updated[target] += (
                            0.85 * scores[source] / len(adjacency[source])
                        )
            if sum(abs(updated[v] - scores[v]) for v in ids) < 1e-10:
                scores = updated
                break
            scores = updated
        return {
            chunk["id"]: scores[chunk["version_id"]]
            for chunk in chunks
            if scores[chunk["version_id"]] > 0
        }

    def search(
        self, plan: SearchPlan, *, provider=None, stages: RankStages | None = None
    ) -> dict:
        stages = stages or RankStages()
        chunks = self.chunks(plan)
        by_id = {chunk["id"]: chunk for chunk in chunks}
        raw = bm25(plan.query, {c["id"]: c["content"] for c in chunks})
        metadata = bm25(
            plan.query,
            {
                c[
                    "id"
                ]: f'{c["resource_label"]} {c["label"]} {c["component"]} {c["content"]}'
                for c in chunks
            },
        )
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
            dense = {
                chunk["id"]: cosine(vector, query_vectors[0][0])
                for group, embedded in zip(groups, vectors, strict=True)
                for chunk, vector in zip(group, embedded, strict=True)
            }
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
            "as_of": str(plan.as_of),
            "eligible_chunks": len(chunks),
            "candidate_count": len(ordered),
            "context_bytes": used,
            "api": api,
            "api_stages": api_stages,
            "hits": hits,
            "dense_status": dense_status,
            "rerank_status": rerank_status,
            "ppr_status": ppr_status,
            "warning": "Recuperación experimental; no determina aplicabilidad al caso concreto.",
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
            key=lambda n: (n["valid_from"], n["id"]),
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
            "policy": "all_reviewed_history_not_current_applicability",
        }
