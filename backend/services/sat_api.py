"""Read primitives adapted from hmartim/sat-graph-api v3 (MIT).

Supported subset and deployment differences are explicit in implementation-guide.
Editorial commands deliberately live outside this canonical read API.
"""
from collections import defaultdict
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from services.quality_access import require_quality_admin
from services.sat_corpus_routes import editor, call

UPSTREAM_COMMIT = "a767a3c47c654087288fd411b81ef2d8047e3696"
router = APIRouter(prefix="/sat-graph/api", tags=["SAT-Graph canonical primitives"],
                   dependencies=[Depends(require_quality_admin)])


class Item(BaseModel):
    id: str
    typeId: str
    label: str
    parentId: str | None = None
    url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Version(BaseModel):
    id: str
    itemId: str
    type: str
    validityInterval: tuple[datetime | None, datetime | None]
    metadata: dict[str, Any] = Field(default_factory=dict)


class TextUnit(BaseModel):
    id: str
    sourceType: Literal["Version"]
    sourceId: str
    language: str
    aspect: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Batch(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=10000)


class TextBatch(BaseModel):
    versionIds: list[str] = Field(min_length=1, max_length=10000)
    language: str = Field(pattern=r"^[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]+)*$")
    aspects: list[str] | None = Field(default=None, min_length=1)


class CanonicalGraph:
    def __init__(self, graph):
        self.nodes = {n["id"]: n for n in graph["nodes"]}
        self.links = defaultdict(list)
        self.parents = {}
        for e in graph["edges"]:
            self.links[(e["source"], e["type"])].append(e["target"])
            if e["type"] == "has_part":
                self.parents[e["target"]] = e["source"]

    def node(self, identity, kinds):
        node = self.nodes.get(identity)
        if not node or node["type"] not in kinds:
            raise HTTPException(404, {"code": "NOT_FOUND", "message": "Identificador inexistente"})
        return node

    def item(self, identity):
        n = self.node(identity, {"Resource", "Work"})
        return {"id": identity, "typeId": n.get("kind", "norm"),
                "label": n.get("label") or n.get("title", identity),
                "parentId": self.parents.get(identity, n.get("resource_id")),
                "url": n.get("url"), "metadata": {"storageType": n["type"]}}

    def version(self, identity):
        n = self.node(identity, {"CTV"})
        iso = lambda s: s + "T00:00:00Z" if s and len(s) == 10 else s
        return {"id": identity, "itemId": n["work_id"], "type": "statutory",
                "validityInterval": [iso(n.get("valid_from")), iso(n.get("valid_to"))],
                "metadata": {"provenance": n.get("provenance_state"),
                             "validityPolicy": "maintained-corpus-no-clock",
                             "legalIntervalKnown": n.get("valid_from") is not None,
                             "editorialSupersededBy": n.get("editorial_superseded_by"),
                             "documentaryRevision": n.get("documentary_revision")}}

    def texts(self, identity, language=None, aspects=None):
        self.node(identity, {"CTV"})  # Missing Version != existing Version with no texts.
        result = []
        for tid in self.links[(identity, "has_text")]:
            t = self.nodes[tid]
            if (language and t["language"] != language) or (aspects is not None and "canonical" not in aspects):
                continue
            result.append({"id": tid, "sourceType": "Version", "sourceId": identity,
                           "language": t["language"], "aspect": "canonical", "content": t["text"],
                           "metadata": {"evidenceId": t.get("evidence_id"), "start": t.get("start"),
                                        "end": t.get("end"), "sha256": t.get("text_sha256")}})
        return result

    def children(self, identity, versions=False):
        if versions:
            self.node(identity, {"CTV"})
            return [self.version(i) for i in self.links[(identity, "contains_version")]]
        self.item(identity)
        return [self.item(n["id"]) for n in self.nodes.values()
                if n["type"] in {"Work", "Resource"} and self.item(n["id"])["parentId"] == identity]

    def hierarchy(self, identity, depth=-1, versions=False):
        (self.version if versions else self.item)(identity)
        seen, queue, result = {identity}, [(identity, 0)], []
        for parent, level in queue:
            if depth >= 0 and level >= depth:
                continue
            for child in self.children(parent, versions):
                if child["id"] not in seen:
                    seen.add(child["id"])
                    result.append(child["id"])
                    queue.append((child["id"], level + 1))
        return result


async def run(fn):
    return await call(lambda: fn(CanonicalGraph(editor().store.export())))


@router.get("/meta/implementation-guide", operation_id="getImplementationGuide")
async def guide():
    return {"upstream": "https://github.com/hmartim/sat-graph-api", "commit": UPSTREAM_COMMIT,
            "specificationVersion": "3.0.0", "conformance": "documented-subset",
            "authentication": "Existing admin session or X-API-Key; not upstream Authorization profile",
            "temporalPolicy": "No clock or mandatory date. Current chat uses latest stored non-superseded edition.",
            "unknownIntervals": "[null, null] means unknown, NOT infinite legal validity; deployment extension.",
            "batchPolicy": "At most 10000 IDs; missing items/versions omitted; text batch missing Version returns 404; never silently truncated.",
            "textMaterialization": "One TextUnit per stored CLV; parent text includes descendants, spans in Unicode codepoints.",
            "editorialCommands": "/sat-graph/review (local extension, not specified upstream)",
            "unsupported": ["ranked discovery", "causality", "applicability", "relations", "transaction-time queries", "historical interval filters"],
            "operations": [r.operation_id for r in router.routes]}


@router.get("/meta/text-unit-aspects", operation_id="getSupportedTextUnitAspects")
async def aspects():
    return [{"value": "canonical", "label": "Texto del corpus", "description": "Transcripción revisable almacenada en CLV"}]


@router.get("/meta/version-types", operation_id="getSupportedVersionTypes")
async def types():
    return [{"value": "statutory", "label": "Normativo", "description": "Estado textual de un componente normativo"}]


@router.post("/items/batch-get", operation_id="getBatchItems", response_model=list[Item])
async def items_batch(body: Batch):
    return await run(lambda g: [g.item(i) for i in dict.fromkeys(body.ids) if g.nodes.get(i, {}).get("type") in {"Work", "Resource"}])


@router.post("/versions/batch-get", operation_id="getBatchVersions", response_model=list[Version])
async def versions_batch(body: Batch):
    return await run(lambda g: [g.version(i) for i in dict.fromkeys(body.ids) if g.nodes.get(i, {}).get("type") == "CTV"])


@router.post("/text-units/batch-get", operation_id="getBatchTextUnits", response_model=list[TextUnit])
async def texts_batch(body: TextBatch):
    return await run(lambda g: [t for v in dict.fromkeys(body.versionIds) for t in g.texts(v, body.language, body.aspects)])


@router.get("/items/{itemId}", operation_id="getItem", response_model=Item)
async def item(itemId: str):
    return await run(lambda g: g.item(itemId))


@router.get("/items/{itemId}/children", operation_id="getItemChildren", response_model=list[Item])
async def children(itemId: str):
    return await run(lambda g: g.children(itemId))


@router.get("/items/{itemId}/hierarchy", operation_id="getItemHierarchy", response_model=list[str])
async def hierarchy(itemId: str, depth: int = -1):
    return await run(lambda g: g.hierarchy(itemId, depth))


@router.get("/items/{itemId}/versions", operation_id="getItemVersions", response_model=list[Version])
async def versions(itemId: str, startAt: datetime | None = None, endAt: datetime | None = None):
    def fetch(g):
        g.item(itemId)
        if startAt or endAt:
            # Unknown legal intervals cannot honestly answer interval-overlap queries.
            raise HTTPException(422, "El perfil de corpus vigente no resuelve intervalos históricos desconocidos")
        items = [g.version(n["id"]) for n in g.nodes.values() if n["type"] == "CTV" and n["work_id"] == itemId]
        return sorted(items, key=lambda v: (v["validityInterval"][0] or "", v["id"]))
    return await run(fetch)


@router.get("/versions/{versionId}", operation_id="getVersion", response_model=Version)
async def version(versionId: str):
    return await run(lambda g: g.version(versionId))


@router.get("/versions/{versionId}/children", operation_id="getVersionChildren", response_model=list[Version])
async def version_children(versionId: str):
    return await run(lambda g: g.children(versionId, True))


@router.get("/versions/{versionId}/hierarchy", operation_id="getVersionHierarchy", response_model=list[str])
async def version_hierarchy(versionId: str, depth: int = -1):
    return await run(lambda g: g.hierarchy(versionId, depth, True))


@router.get("/versions/{versionId}/text-units", operation_id="getVersionTextUnits", response_model=list[TextUnit])
async def version_texts(versionId: str, language: str | None = None,
                        aspects: list[str] | None = Query(default=None, min_length=1)):
    return await run(lambda g: g.texts(versionId, language, aspects))


@router.get("/text-units/{textUnitId}", operation_id="getTextUnit", response_model=TextUnit)
async def text_unit(textUnitId: str):
    def fetch(g):
        g.node(textUnitId, {"CLV"})
        for (vid, predicate), ids in g.links.items():
            if predicate == "has_text" and textUnitId in ids:
                return next(t for t in g.texts(vid) if t["id"] == textUnitId)
        raise HTTPException(404, "TextUnit sin Version")
    return await run(fetch)
