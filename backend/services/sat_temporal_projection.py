"""Pure projection from SATGraphStore exports to SAT-Graph Viewer datasets.

Maintains IA_juridica's temporal honesty invariant: when a CTV carries
``valid_from = None``, its projected ``validityInterval`` stays ``(None, None)``
with ``metadata["legalIntervalKnown"] = False``. Editorial revisions are kept
distinct from normative legislative or judicial actions.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from threading import RLock
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from services.sat_corpus import _review_index


class UnknownResourceError(KeyError):
    """Raised when a requested SAT resource_id does not exist in the graph."""


class ViewerItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    typeId: str
    label: str
    parentId: str | None = None
    url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ViewerVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    itemId: str
    type: Literal["statutory", "interpretive"]
    validityInterval: tuple[str | None, str | None]
    metadata: dict[str, Any] = Field(default_factory=dict)


class ViewerAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    eventTime: str | None = None
    terminatesVersionIds: list[str] = Field(default_factory=list)
    producesVersionIds: list[str] = Field(default_factory=list)
    sourceId: str | None = None
    label: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ViewerTextUnit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    sourceType: Literal["Version"] = "Version"
    sourceId: str
    language: str
    aspect: str = "canonical"
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ViewerDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: str = "sat-graph-viewer/1"
    source: Literal["live-corpus", "bundled-sample", "uploaded-json"] = "live-corpus"
    resourceId: str | None = None
    title: str
    policyNote: str
    items: list[ViewerItem]
    versions: list[ViewerVersion]
    actions: list[ViewerAction]
    textUnits: list[ViewerTextUnit]
    metadata: dict[str, Any] = Field(default_factory=dict)


_TEMPORAL_EDGE_LOCK = RLock()
_TEMPORAL_EDGE_CACHE: dict[tuple[int, int, int], dict[str, Any]] = {}
_MAX_EDGE_CACHE = 8


def _temporal_edge_index(graph: dict[str, Any]) -> dict[str, Any]:
    """Cache temporal-specific edges keyed by the exact exported graph object."""
    key = (id(graph), len(graph["nodes"]), len(graph["edges"]))
    with _TEMPORAL_EDGE_LOCK:
        cached = _TEMPORAL_EDGE_CACHE.get(key)
    if cached is not None and cached["graph"] is graph:
        return cached

    work_parents: dict[str, str] = {}
    action_sources: dict[str, str] = {}
    action_terminates: dict[str, list[str]] = defaultdict(list)
    action_produces: dict[str, list[str]] = defaultdict(list)
    amended_by: dict[str, list[str]] = defaultdict(list)

    for edge in graph["edges"]:
        etype = edge["type"]
        if etype == "has_part":
            work_parents[edge["target"]] = edge["source"]
        elif etype == "source":
            action_sources[edge["source"]] = edge["target"]
        elif etype == "terminates":
            action_terminates[edge["source"]].append(edge["target"])
        elif etype == "produces":
            action_produces[edge["source"]].append(edge["target"])
        elif etype == "amended_by":
            amended_by[edge["source"]].append(edge["target"])

    entry = {
        "graph": graph,
        "work_parents": work_parents,
        "action_sources": action_sources,
        "action_terminates": {k: tuple(v) for k, v in action_terminates.items()},
        "action_produces": {k: tuple(v) for k, v in action_produces.items()},
        "amended_by": {k: tuple(v) for k, v in amended_by.items()},
    }
    with _TEMPORAL_EDGE_LOCK:
        if len(_TEMPORAL_EDGE_CACHE) >= _MAX_EDGE_CACHE:
            _TEMPORAL_EDGE_CACHE.clear()
        _TEMPORAL_EDGE_CACHE[key] = entry
    return entry


def normalize_instant_iso(value: str | date | datetime | None) -> str | None:
    """Normalize YYYY-MM-DD dates and offset-aware ISO timestamps to UTC RFC 3339."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("Timestamp must include an explicit timezone offset")
        return _format_utc_datetime(value.astimezone(timezone.utc))
    if isinstance(value, date):
        return f"{value.isoformat()}T00:00:00Z"

    raw = str(value).strip()
    if not raw:
        return None
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        parsed_date = date.fromisoformat(raw)
        return f"{parsed_date.isoformat()}T00:00:00Z"

    normalized_raw = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
    parsed_dt = datetime.fromisoformat(normalized_raw)
    if parsed_dt.tzinfo is None:
        raise ValueError(f"Timestamp lacks explicit timezone offset: {raw}")
    return _format_utc_datetime(parsed_dt.astimezone(timezone.utc))


def _format_utc_datetime(dt: datetime) -> str:
    if dt.microsecond == 0:
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _safe_normalize_instant(value: str | date | datetime | None) -> str | None:
    try:
        return normalize_instant_iso(value)
    except ValueError:
        return None


def _version_kind(ctv: dict[str, Any]) -> Literal["statutory", "interpretive"]:
    if ctv.get("version_type") == "interpretive" or ctv.get("provenance_state") == "interpretive":
        return "interpretive"
    return "statutory"


def _build_policy_note(
    *,
    legal_known_count: int,
    unknown_snapshot_count: int,
    editorial_action_count: int,
) -> str:
    parts = [
        "Las versiones con validityInterval [null, null] corresponden a capturas verificadas del corpus cuyo intervalo legal no se infiere ni sintetiza."
    ]
    if legal_known_count > 0 and unknown_snapshot_count > 0:
        parts.append(
            f"Este conjunto combina {legal_known_count} versiones con intervalo legal explícito y {unknown_snapshot_count} capturas sin fecha legal."
        )
    elif unknown_snapshot_count > 0:
        parts.append(
            f"Las {unknown_snapshot_count} versiones proyectadas tienen intervalo legal desconocido (legalIntervalKnown: false)."
        )
    if editorial_action_count > 0:
        parts.append(
            "Las acciones con kind 'editorial_revision' registran revisiones de transcripción editorial y no reformas legales."
        )
    return " ".join(parts)


def project_sat_graph_to_viewer_dataset(
    graph: dict[str, Any],
    resource_id: str | None = None,
    *,
    include_editorial_history: bool = True,
) -> ViewerDataset:
    """Project an exported SATGraphStore graph into a SAT-Graph Viewer dataset."""
    idx = _review_index(graph)
    edges = _temporal_edge_index(graph)
    nodes: dict[str, dict[str, Any]] = idx["nodes"]
    eligible: set[str] = idx["eligible"]
    outgoing = idx["outgoing"]
    ctvs_by_resource = idx["ctvs_by_resource"]
    history_by_resource = idx["history_by_resource"]

    works_by_resource: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes.values():
        if node["type"] == "Work":
            works_by_resource[node["resource_id"]].append(node)

    if resource_id is not None:
        resource_exists = (
            resource_id in ctvs_by_resource
            or resource_id in works_by_resource
            or (resource_id in nodes and nodes[resource_id]["type"] == "Resource")
        )
        if not resource_exists:
            raise UnknownResourceError(f"Recurso SAT no encontrado: {resource_id}")
        target_resource_ids = [resource_id]
    else:
        target_resource_ids = sorted(set(ctvs_by_resource.keys()) | set(works_by_resource.keys()))

    target_resource_set = set(target_resource_ids)

    raw_items: list[ViewerItem] = []
    projected_item_ids: set[str] = set()
    projected_work_ids: set[str] = set()

    for rid in target_resource_ids:
        res_node = nodes.get(rid)
        if res_node and res_node["type"] == "Resource":
            projected_item_ids.add(rid)
            raw_items.append(
                ViewerItem(
                    id=rid,
                    typeId=res_node.get("kind") or "norm",
                    label=res_node.get("title") or res_node.get("label") or rid,
                    parentId=None,
                    url=res_node.get("url"),
                    metadata={
                        "storageType": "Resource",
                        "resourceId": rid,
                    },
                )
            )

    work_nodes: list[dict[str, Any]] = []
    for rid in target_resource_ids:
        for w in works_by_resource.get(rid, ()):
            projected_item_ids.add(w["id"])
            projected_work_ids.add(w["id"])
            work_nodes.append(w)

    work_parents: dict[str, str] = edges["work_parents"]
    for w in sorted(work_nodes, key=lambda n: (n.get("resource_id", ""), n["id"])):
        parent_candidate = work_parents.get(w["id"], w.get("resource_id"))
        parent_id = parent_candidate if parent_candidate in projected_item_ids and parent_candidate != w["id"] else None
        raw_items.append(
            ViewerItem(
                id=w["id"],
                typeId=w.get("kind") or "component",
                label=w.get("label") or w.get("component") or w["id"],
                parentId=parent_id,
                url=w.get("url"),
                metadata={
                    "storageType": "Work",
                    "resourceId": w.get("resource_id"),
                    "component": w.get("component"),
                },
            )
        )

    versions: list[ViewerVersion] = []
    projected_version_ids: set[str] = set()
    ctvs_by_revision: dict[str, list[str]] = defaultdict(list)
    projected_ctv_nodes: list[dict[str, Any]] = []

    for rid in target_resource_ids:
        for ctv in ctvs_by_resource.get(rid, ()):
            if ctv["work_id"] not in projected_work_ids:
                continue
            projected_ctv_nodes.append(ctv)
            projected_version_ids.add(ctv["id"])
            if ctv.get("documentary_revision"):
                ctvs_by_revision[ctv["documentary_revision"]].append(ctv["id"])

            valid_from_raw = ctv.get("valid_from")
            valid_to_raw = ctv.get("valid_to")
            if valid_from_raw is None:
                validity_interval: tuple[str | None, str | None] = (None, None)
                legal_interval_known = False
            else:
                validity_interval = (
                    normalize_instant_iso(valid_from_raw),
                    normalize_instant_iso(valid_to_raw),
                )
                legal_interval_known = True

            meta: dict[str, Any] = {
                "legalIntervalKnown": legal_interval_known,
                "snapshotAsOf": _safe_normalize_instant(ctv.get("snapshot_as_of")),
                "provenance": ctv.get("provenance_state"),
                "editorialSupersededBy": ctv.get("editorial_superseded_by"),
                "documentaryRevision": ctv.get("documentary_revision"),
                "archived": bool(ctv.get("editorial_superseded_by")),
                "retrievable": ctv["id"] in eligible,
            }
            if ctv.get("scope") is not None:
                meta["scope"] = ctv.get("scope")
            if ctv.get("checked_through") is not None:
                meta["checkedThrough"] = ctv.get("checked_through")
            if ctv.get("amending_source") is not None:
                meta["amendingSource"] = ctv.get("amending_source")

            versions.append(
                ViewerVersion(
                    id=ctv["id"],
                    itemId=ctv["work_id"],
                    type=_version_kind(ctv),
                    validityInterval=validity_interval,
                    metadata=meta,
                )
            )

    versions.sort(key=lambda v: (v.validityInterval[0] is None, v.validityInterval[0] or "", v.itemId, v.id))

    text_units: list[ViewerTextUnit] = []
    for version in versions:
        for tid in outgoing.get((version.id, "has_text"), ()):
            clv = nodes.get(tid)
            if not clv or clv.get("type") != "CLV":
                continue
            text_units.append(
                ViewerTextUnit(
                    id=tid,
                    sourceType="Version",
                    sourceId=version.id,
                    language=clv.get("language") or "es",
                    aspect=clv.get("aspect") or "canonical",
                    content=clv.get("text") or "",
                    metadata={
                        "evidenceId": clv.get("evidence_id"),
                        "start": clv.get("start"),
                        "end": clv.get("end"),
                        "sha256": clv.get("text_sha256"),
                    },
                )
            )

    actions: list[ViewerAction] = []
    normative_produced_versions: set[str] = set()
    action_sources: dict[str, str] = edges["action_sources"]
    action_terminates: dict[str, tuple[str, ...]] = edges["action_terminates"]
    action_produces: dict[str, tuple[str, ...]] = edges["action_produces"]

    for node in nodes.values():
        if node["type"] != "Action":
            continue
        aid = node["id"]
        terminates = [
            vid
            for vid in dict.fromkeys([*(node.get("terminates") or ()), *action_terminates.get(aid, ())])
            if vid in projected_version_ids
        ]
        produces = [
            vid
            for vid in dict.fromkeys([*(node.get("produces") or ()), *action_produces.get(aid, ())])
            if vid in projected_version_ids
        ]
        if not terminates and not produces:
            continue
        normative_produced_versions.update(produces)
        raw_time = node.get("effective_on") or node.get("event_time") or node.get("effective_time")
        kind = node.get("kind") or "amend"
        actions.append(
            ViewerAction(
                id=aid,
                kind=kind,
                eventTime=_safe_normalize_instant(raw_time),
                terminatesVersionIds=terminates,
                producesVersionIds=produces,
                sourceId=action_sources.get(aid) or node.get("source_resource_id"),
                label=node.get("label") or node.get("action_key") or f"{kind}: {aid}",
                metadata={
                    "syntheticKind": "normative",
                    "actionKey": node.get("action_key"),
                    "reviewId": node.get("review_id"),
                    "evidenceId": node.get("evidence_id"),
                },
            )
        )

    amended_by_edges: dict[str, tuple[str, ...]] = edges["amended_by"]
    for ctv in sorted(projected_ctv_nodes, key=lambda n: n["id"]):
        if ctv["id"] in normative_produced_versions:
            continue
        amending_source = ctv.get("amending_source")
        edge_sources = amended_by_edges.get(ctv["id"], ())
        if not amending_source and not edge_sources:
            continue
        if isinstance(amending_source, dict):
            src_id = amending_source.get("id") or (edge_sources[0] if edge_sources else None)
            src_title = amending_source.get("title") or src_id or "Fuente modificatoria"
            src_url = amending_source.get("url")
        else:
            src_id = str(amending_source) if amending_source else edge_sources[0]
            src_node = nodes.get(src_id, {})
            src_title = src_node.get("title") or src_id
            src_url = src_node.get("url")
        actions.append(
            ViewerAction(
                id=f"amend-ref:{ctv['id']}:{src_id or 'unknown'}",
                kind="amend_reference",
                eventTime=None,
                terminatesVersionIds=[],
                producesVersionIds=[ctv["id"]],
                sourceId=src_id,
                label=f"Referencia modificatoria: {src_title}",
                metadata={
                    "syntheticKind": "normative_reference",
                    "legalDateKnown": False,
                    "sourceUrl": src_url,
                },
            )
        )

    if include_editorial_history:
        for rid in sorted(target_resource_set):
            for review in history_by_resource.get(rid, ()):
                prev_rev = review.get("previous_revision")
                new_rev = review.get("revision")
                terminates = sorted(
                    vid for vid in ctvs_by_revision.get(prev_rev, ()) if vid in projected_version_ids
                )
                produces = sorted(
                    vid for vid in ctvs_by_revision.get(new_rev, ()) if vid in projected_version_ids
                )
                actions.append(
                    ViewerAction(
                        id=review["id"],
                        kind="editorial_revision",
                        eventTime=_safe_normalize_instant(review.get("recorded_at")),
                        terminatesVersionIds=terminates,
                        producesVersionIds=produces,
                        sourceId=rid,
                        label=review.get("reason") or "Revisión editorial",
                        metadata={
                            "syntheticKind": "editorial",
                            "reviewer": review.get("reviewer"),
                            "previousRevision": prev_rev,
                            "revision": new_rev,
                            "rule": review.get("rule"),
                            "componentCount": review.get("component_count"),
                        },
                    )
                )

    actions.sort(key=lambda a: (a.eventTime is None, a.eventTime or "", a.id))

    legal_known_count = sum(1 for v in versions if v.metadata.get("legalIntervalKnown"))
    unknown_snapshot_count = len(versions) - legal_known_count
    normative_action_count = sum(1 for a in actions if a.metadata.get("syntheticKind") == "normative")
    editorial_action_count = sum(1 for a in actions if a.metadata.get("syntheticKind") == "editorial")

    if resource_id is not None:
        res_node = nodes.get(resource_id)
        title = (res_node.get("title") if res_node else None) or resource_id
    else:
        title = f"Corpus SAT completo ({len(target_resource_ids)} normas)"

    return ViewerDataset(
        schemaVersion="sat-graph-viewer/1",
        source="live-corpus",
        resourceId=resource_id,
        title=title,
        policyNote=_build_policy_note(
            legal_known_count=legal_known_count,
            unknown_snapshot_count=unknown_snapshot_count,
            editorial_action_count=editorial_action_count,
        ),
        items=raw_items,
        versions=versions,
        actions=actions,
        textUnits=text_units,
        metadata={
            "includeEditorialHistory": include_editorial_history,
            "resourceCount": len(target_resource_ids),
            "legalIntervalKnownCount": legal_known_count,
            "unknownSnapshotCount": unknown_snapshot_count,
            "normativeActionCount": normative_action_count,
            "editorialActionCount": editorial_action_count,
        },
    )


def bundled_viewer_samples() -> list[dict[str, Any]]:
    """Return validated offline sample datasets for the SAT-Graph Viewer."""
    amendment_chain = ViewerDataset(
        schemaVersion="sat-graph-viewer/1",
        source="bundled-sample",
        resourceId="pe:ley:28970-sample",
        title="Cadena de reformas normativas — Ley N.° 28970 (REDAM, Art. 1)",
        policyNote=(
            "Ejemplo demostrativo con intervalos legales semiabiertos [inicio, fin) "
            "para verificar recuperación puntual exacta, transiciones sin solapamiento "
            "y comparación textual entre versiones sucesivas."
        ),
        items=[
            ViewerItem(
                id="sample:pe:ley:28970",
                typeId="norm",
                label="Ley N.° 28970 — Registro de Deudores Alimentarios Morosos (REDAM)",
                parentId=None,
                url="https://spij.minjus.gob.pe/",
                metadata={"jurisdiction": "PE", "storageType": "Resource"},
            ),
            ViewerItem(
                id="sample:pe:ley:28970/art-1",
                typeId="article",
                label="Artículo 1. Creación del Registro de Deudores Alimentarios Morosos",
                parentId="sample:pe:ley:28970",
                metadata={"jurisdiction": "PE", "storageType": "Work", "component": "art-1"},
            ),
        ],
        versions=[
            ViewerVersion(
                id="sample:v:28970:art1:v1",
                itemId="sample:pe:ley:28970/art-1",
                type="statutory",
                validityInterval=("2007-01-27T00:00:00Z", "2018-09-12T00:00:00Z"),
                metadata={
                    "legalIntervalKnown": True,
                    "provenance": "reviewed",
                    "scope": "PE",
                    "editionLabel": "Texto original (Ley N.° 28970)",
                },
            ),
            ViewerVersion(
                id="sample:v:28970:art1:v2",
                itemId="sample:pe:ley:28970/art-1",
                type="statutory",
                validityInterval=("2018-09-12T00:00:00Z", "2024-03-15T00:00:00Z"),
                metadata={
                    "legalIntervalKnown": True,
                    "provenance": "reviewed",
                    "scope": "PE",
                    "editionLabel": "Modificación por Decreto Legislativo N.° 1377",
                },
            ),
            ViewerVersion(
                id="sample:v:28970:art1:v3",
                itemId="sample:pe:ley:28970/art-1",
                type="statutory",
                validityInterval=("2024-03-15T00:00:00Z", None),
                metadata={
                    "legalIntervalKnown": True,
                    "provenance": "reviewed",
                    "scope": "PE",
                    "editionLabel": "Actualización de interoperabilidad digital",
                },
            ),
        ],
        actions=[
            ViewerAction(
                id="sample:act:28970:enact",
                kind="enact",
                eventTime="2007-01-27T00:00:00Z",
                terminatesVersionIds=[],
                producesVersionIds=["sample:v:28970:art1:v1"],
                sourceId="sample:pe:ley:28970",
                label="Promulgación de la Ley N.° 28970",
                metadata={"syntheticKind": "normative"},
            ),
            ViewerAction(
                id="sample:act:28970:amend-1377",
                kind="amend",
                eventTime="2018-09-12T00:00:00Z",
                terminatesVersionIds=["sample:v:28970:art1:v1"],
                producesVersionIds=["sample:v:28970:art1:v2"],
                sourceId="pe:dl:1377",
                label="Reforma del Art. 1 mediante Decreto Legislativo N.° 1377",
                metadata={"syntheticKind": "normative"},
            ),
            ViewerAction(
                id="sample:act:28970:amend-2024",
                kind="amend",
                eventTime="2024-03-15T00:00:00Z",
                terminatesVersionIds=["sample:v:28970:art1:v2"],
                producesVersionIds=["sample:v:28970:art1:v3"],
                sourceId="pe:ley:31990-ref",
                label="Reforma de interoperabilidad registral del REDAM",
                metadata={"syntheticKind": "normative"},
            ),
        ],
        textUnits=[
            ViewerTextUnit(
                id="sample:tu:28970:art1:v1:es",
                sourceType="Version",
                sourceId="sample:v:28970:art1:v1",
                language="es",
                aspect="canonical",
                content=(
                    "Artículo 1. Créase en el Órgano de Gobierno del Poder Judicial "
                    "el Registro de Deudores Alimentarios Morosos, donde serán inscritas "
                    "las personas que adeuden tres cuotas, sucesivas o no, de sus obligaciones "
                    "alimentarias establecidas en sentencias consentidas o ejecutoriadas."
                ),
                metadata={"edition": "2007"},
            ),
            ViewerTextUnit(
                id="sample:tu:28970:art1:v2:es",
                sourceType="Version",
                sourceId="sample:v:28970:art1:v2",
                language="es",
                aspect="canonical",
                content=(
                    "Artículo 1. Créase en el Órgano de Gobierno del Poder Judicial "
                    "el Registro de Deudores Alimentarios Morosos, donde serán inscritas "
                    "las personas que adeuden tres cuotas, sucesivas o no, de sus obligaciones "
                    "alimentarias establecidas en sentencias consentidas o ejecutoriadas, "
                    "o en acuerdos conciliatorios con calidad de cosa juzgada."
                ),
                metadata={"edition": "2018"},
            ),
            ViewerTextUnit(
                id="sample:tu:28970:art1:v3:es",
                sourceType="Version",
                sourceId="sample:v:28970:art1:v3",
                language="es",
                aspect="canonical",
                content=(
                    "Artículo 1. El Poder Judicial administra el Registro de Deudores "
                    "Alimentarios Morosos en plataforma interoperable de acceso público, "
                    "donde se inscriben las personas que adeuden tres cuotas, sucesivas o no, "
                    "de obligaciones alimentarias fijadas por sentencia firme o acta de "
                    "conciliación con calidad de cosa juzgada."
                ),
                metadata={"edition": "2024"},
            ),
        ],
        metadata={"sampleKind": "amendment_chain", "jurisdiction": "PE"},
    )

    interpretive_overlay = ViewerDataset(
        schemaVersion="sat-graph-viewer/1",
        source="bundled-sample",
        resourceId="pe:ley:30364-sample",
        title="Superposición normativa e interpretativa — Ley N.° 30364 (Art. 16)",
        policyNote=(
            "Ejemplo demostrativo de parsimonia ontológica SAT-Graph: las versiones "
            "interpretativas (I-TV) de órganos jurisdiccionales se superponen sobre la "
            "versión normativa vigente (S-TV) sin terminar su intervalo legal."
        ),
        items=[
            ViewerItem(
                id="sample:pe:ley:30364",
                typeId="norm",
                label="Ley N.° 30364 — Prevención, sanción y erradicación de la violencia contra las mujeres",
                parentId=None,
                url="https://spij.minjus.gob.pe/",
                metadata={"jurisdiction": "PE", "storageType": "Resource"},
            ),
            ViewerItem(
                id="sample:pe:ley:30364/art-16",
                typeId="article",
                label="Artículo 16. Proceso especial y medidas de protección",
                parentId="sample:pe:ley:30364",
                metadata={"jurisdiction": "PE", "storageType": "Work", "component": "art-16"},
            ),
        ],
        versions=[
            ViewerVersion(
                id="sample:v:30364:art16:stv-1",
                itemId="sample:pe:ley:30364/art-16",
                type="statutory",
                validityInterval=("2015-11-23T00:00:00Z", None),
                metadata={
                    "legalIntervalKnown": True,
                    "provenance": "reviewed",
                    "scope": "PE",
                    "authority": "Congreso de la República",
                },
            ),
            ViewerVersion(
                id="sample:v:30364:art16:itv-csj",
                itemId="sample:pe:ley:30364/art-16",
                type="interpretive",
                validityInterval=("2019-09-10T00:00:00Z", "2023-06-01T00:00:00Z"),
                metadata={
                    "legalIntervalKnown": True,
                    "provenance": "interpretive",
                    "scope": "PE",
                    "authority": "Corte Suprema de Justicia — Acuerdo Plenario",
                },
            ),
            ViewerVersion(
                id="sample:v:30364:art16:itv-tc",
                itemId="sample:pe:ley:30364/art-16",
                type="interpretive",
                validityInterval=("2021-11-18T00:00:00Z", None),
                metadata={
                    "legalIntervalKnown": True,
                    "provenance": "interpretive",
                    "scope": "PE",
                    "authority": "Tribunal Constitucional — Doctrina Jurisprudencial",
                },
            ),
        ],
        actions=[
            ViewerAction(
                id="sample:act:30364:enact",
                kind="enact",
                eventTime="2015-11-23T00:00:00Z",
                terminatesVersionIds=[],
                producesVersionIds=["sample:v:30364:art16:stv-1"],
                sourceId="sample:pe:ley:30364",
                label="Promulgación de la Ley N.° 30364",
                metadata={"syntheticKind": "normative"},
            ),
            ViewerAction(
                id="sample:act:30364:interpret-csj",
                kind="interpret",
                eventTime="2019-09-10T00:00:00Z",
                terminatesVersionIds=[],
                producesVersionIds=["sample:v:30364:art16:itv-csj"],
                sourceId="pe:csj:ap-09-2019",
                label="Acuerdo Plenario sobre plazo y estándar probatorio de medidas de protección",
                metadata={"syntheticKind": "normative"},
            ),
            ViewerAction(
                id="sample:act:30364:interpret-tc",
                kind="interpret",
                eventTime="2021-11-18T00:00:00Z",
                terminatesVersionIds=[],
                producesVersionIds=["sample:v:30364:art16:itv-tc"],
                sourceId="pe:tc:exp-03378-2019",
                label="Sentencia del Tribunal Constitucional sobre debida diligencia reforzada",
                metadata={"syntheticKind": "normative"},
            ),
        ],
        textUnits=[
            ViewerTextUnit(
                id="sample:tu:30364:art16:stv1:es",
                sourceType="Version",
                sourceId="sample:v:30364:art16:stv-1",
                language="es",
                aspect="canonical",
                content=(
                    "Artículo 16. El juzgado de familia evalúa el riesgo y dicta las medidas "
                    "de protección idóneas en el plazo máximo legal, considerando la ficha de "
                    "valoración del riesgo y las circunstancias particulares de la víctima."
                ),
                metadata={"track": "statutory"},
            ),
            ViewerTextUnit(
                id="sample:tu:30364:art16:itv-csj:es",
                sourceType="Version",
                sourceId="sample:v:30364:art16:itv-csj",
                language="es",
                aspect="holding",
                content=(
                    "Criterio plenario: en escenarios de riesgo severo, la emisión de medidas "
                    "de protección procede de modo inmediato con base en la ficha de valoración, "
                    "sin exigir audiencia previa cuando ello comprometa la integridad de la víctima."
                ),
                metadata={"track": "interpretive", "court": "Corte Suprema"},
            ),
            ViewerTextUnit(
                id="sample:tu:30364:art16:itv-tc:es",
                sourceType="Version",
                sourceId="sample:v:30364:art16:itv-tc",
                language="es",
                aspect="ratio",
                content=(
                    "Doctrina constitucional: las medidas de protección deben motivarse con "
                    "enfoque de debida diligencia reforzada y mantenerse vigentes mientras "
                    "subsista el riesgo acreditado, coexistiendo con la supervisión judicial periódica."
                ),
                metadata={"track": "interpretive", "court": "Tribunal Constitucional"},
            ),
        ],
        metadata={"sampleKind": "interpretive_overlay", "jurisdiction": "PE"},
    )

    return [
        {
            "id": "pe-amendment-chain",
            "title": amendment_chain.title,
            "description": (
                "Tres versiones normativas sucesivas (2007, 2018, 2024) con transiciones "
                "semiabiertas [inicio, fin) exactas y acciones enact/amend."
            ),
            "dataset": amendment_chain.model_dump(),
        },
        {
            "id": "pe-interpretive-overlay",
            "title": interpretive_overlay.title,
            "description": (
                "Una versión normativa vigente (S-TV) superpuesta concurrentemente por dos "
                "versiones interpretativas judiciales (I-TV) sin derogar la norma base."
            ),
            "dataset": interpretive_overlay.model_dump(),
        },
    ]
