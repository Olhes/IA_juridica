"""Editorial review of the *actual* SAT corpus, not a second visualization store.

Original evidence is immutable. Publishing creates a new documentary/CTV/CLV
edition and retires the previous editorial edition in one transaction.
No legal dates are inferred. Work identities survive corrections.
"""
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from hashlib import file_digest, sha256
from difflib import SequenceMatcher
from pathlib import Path
from threading import RLock
import json
import uuid

from pydantic import BaseModel, ConfigDict, Field

from ingestion.sat_graph.store import SATGraphStore, canonical, digest, work_id
from ingestion.sat_graph.surreal import SurrealSATGraphStore
from ingestion.source_evidence import SourceEvidence
from retrieval.sat import eligible_version_ids


class Conflict(ValueError):
    pass


class Component(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=4000)
    kind: str = Field(min_length=1, max_length=60)
    parent_id: str | None = None
    start: int = Field(ge=0, strict=True)
    end: int = Field(ge=1, strict=True)


class Edition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str = Field(min_length=1, max_length=200)
    markdown: str = Field(min_length=1, max_length=5_000_000)
    components: list[Component] = Field(min_length=1, max_length=10000)


class Publication(BaseModel):
    model_config = ConfigDict(extra="forbid")
    edition: Edition
    reason: str = Field(min_length=3, max_length=2000)


class TextEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    edition: Edition
    component_id: str
    text: str = Field(min_length=1, max_length=5_000_000)


@dataclass(frozen=True)
class OfficialEditionSource:
    """Datos del importador local, no aceptados desde el endpoint de edición."""
    evidence: SourceEvidence
    pdf_name: str
    url: str
    edition_as_of: date
    resource: dict
    historical_quotations: tuple[str, ...] = ()
    amendments: tuple[tuple[str, str], ...] = ()


def validate_edition(edition):
    nodes = {n.id: n for n in edition.components}
    if len(nodes) != len(edition.components):
        raise ValueError("Identificadores de componentes duplicados")
    for n in nodes.values():
        if not n.label.strip() or not n.kind.strip() or not 0 <= n.start < n.end <= len(edition.markdown):
            raise ValueError(f"Etiqueta o rango de texto inválido: {n.label}")
        if n.parent_id:
            parent = nodes.get(n.parent_id)
            if not parent or not parent.start <= n.start < n.end <= parent.end:
                raise ValueError(f"El texto de «{n.label}» debe estar dentro de su padre")
        seen = {n.id}
        parent_id = n.parent_id
        while parent_id:
            if parent_id in seen:
                raise ValueError("La jerarquía contiene un ciclo")
            seen.add(parent_id)
            parent = nodes.get(parent_id)
            if parent is None:
                raise ValueError("Componente padre inexistente")
            parent_id = parent.parent_id
    return edition


def replace_text(edit: TextEdit):
    """Rebase Unicode codepoint spans, including enclosing and nested components.

    A replacement crossing a structural boundary must be resolved explicitly by
    the editor; silently guessing would associate the wrong text with a node.
    """
    edition = edit.edition.model_copy(deep=True)
    validate_edition(edition)
    target = next((n for n in edition.components if n.id == edit.component_id), None)
    if target is None:
        raise ValueError("Componente inexistente")
    old = edition.markdown[target.start:target.end]
    start, end = target.start, target.end
    # Compare only the changed window: a small cleanup in a large root should
    # not require a diff over the whole document.
    left, old_right, new_right = 0, len(old), len(edit.text)
    while left < min(old_right, new_right) and old[left] == edit.text[left]:
        left += 1
    while old_right > left and new_right > left and old[old_right - 1] == edit.text[new_right - 1]:
        old_right -= 1
        new_right -= 1
    before, after = old[left:old_right], edit.text[left:new_right]
    if before and not after:
        # Repeated heading prefixes can slide an exact deletion into the next
        # node. Prefer a matching whole-component deletion when available.
        size = len(before)
        for node in edition.components:
            offset = node.start - start
            if (node.id != target.id and 0 <= offset <= left
                    and node.end - node.start == size
                    and old[:offset] + old[offset + size:] == edit.text):
                left, old_right = offset, offset + size
                before = old[left:old_right]
                break
    if not before or not after:
        changes = [(start + left, start + old_right, after)] if before or after else []
    else:
        if max(len(before), len(after)) > 200_000:
            raise ValueError("Edite los fragmentos alejados por separado: el tramo a comparar supera 200.000 caracteres.")
        changes = [(start + left + a, start + left + b, after[c:d])
                   for tag, a, b, c, d in SequenceMatcher(None, before, after).get_opcodes()
                   if tag != "equal"]
    # Map original boundaries in one pass. Insertions at a start belong to the
    # following component; insertions at its end belong to the preceding one.
    def boundary(pos, is_end, node):
        delta = 0
        for a, b, replacement in changes:
            if a < pos < b:
                raise ValueError(f"La edición cruza el límite de «{node.label}». Edite ese componente primero o ajuste sus rangos.")
            if b < pos or (a != b and b == pos) or (a == b == pos and is_end):
                delta += len(replacement) - (b - a)
        return pos + delta
    removed = set()
    for n in edition.components:
        if n.id != target.id and any(a <= n.start and n.end <= b and not replacement
                                     for a, b, replacement in changes):
            removed.add(n.id)
            continue
        if n.end <= start:
            continue
        if n.start >= end:
            delta = len(edit.text) - len(old)
            n.start += delta
            n.end += delta
            continue
        new_start, new_end = boundary(n.start, False, n), boundary(n.end, True, n)
        if new_start == new_end:
            raise ValueError(f"«{n.label}» quedó sin texto. Conserva un fragmento o usa «Quitar nodo».")
        n.start, n.end = new_start, new_end
    edition.components = [n for n in edition.components if n.id not in removed]
    edition.markdown = edit.edition.markdown[:start] + edit.text + edit.edition.markdown[end:]
    return validate_edition(edition)


_REVIEW_INDEX_LOCK = RLock()
_REVIEW_INDEX_CACHE: dict[tuple[int, int, int], dict] = {}
_MAX_REVIEW_INDEX_CACHE = 8

_FILE_JSON_LOCK = RLock()
_FILE_JSON_CACHE: dict[tuple[str, int, int], object] = {}

_PDF_HASH_LOCK = RLock()
_PDF_HASH_CACHE: dict[tuple[str, int, int], str] = {}


def cached_file_sha256(path: Path) -> str:
    """Compute file SHA-256 via streaming digest, cached by (path, mtime_ns, size)."""
    resolved = path.resolve()
    stat = resolved.stat()
    key = (str(resolved), stat.st_mtime_ns, stat.st_size)
    with _PDF_HASH_LOCK:
        cached = _PDF_HASH_CACHE.get(key)
    if cached is not None:
        return cached
    with resolved.open("rb") as handle:
        value = file_digest(handle, "sha256").hexdigest()
    with _PDF_HASH_LOCK:
        if len(_PDF_HASH_CACHE) >= 128:
            _PDF_HASH_CACHE.clear()
        _PDF_HASH_CACHE[key] = value
    return value


def _cached_json(path: Path):
    resolved = path.resolve()
    stat = resolved.stat()
    key = (str(resolved), stat.st_mtime_ns, stat.st_size)
    with _FILE_JSON_LOCK:
        cached = _FILE_JSON_CACHE.get(key)
    if cached is not None:
        return cached
    parsed = json.loads(resolved.read_text(encoding="utf-8"))
    with _FILE_JSON_LOCK:
        if len(_FILE_JSON_CACHE) >= 256:
            _FILE_JSON_CACHE.clear()
        _FILE_JSON_CACHE[key] = parsed
    return parsed


def _review_index(graph: dict) -> dict:
    """Build or reuse a read-only index of nodes, edges, eligibility, and summaries."""
    key = (id(graph), len(graph["nodes"]), len(graph["edges"]))
    with _REVIEW_INDEX_LOCK:
        cached = _REVIEW_INDEX_CACHE.get(key)
    if cached is not None and cached["graph"] is graph:
        return cached
    nodes = {node["id"]: node for node in graph["nodes"]}
    outgoing = defaultdict(list)
    parents = {}
    ctv_parents = {}
    derived = {}
    for edge in graph["edges"]:
        etype = edge["type"]
        if etype == "has_text":
            outgoing[(edge["source"], "has_text")].append(edge["target"])
        elif etype == "documentary_has_part":
            parents[edge["target"]] = edge["source"]
        elif etype == "contains_version":
            ctv_parents[edge["target"]] = edge["source"]
        elif etype == "derived_from_documentary":
            derived[edge["source"]] = edge["target"]
    eligible = eligible_version_ids(nodes, outgoing)
    summaries = _document_summaries(nodes, eligible)
    summaries_by_id = {d["id"]: d for d in summaries}
    ctvs_by_resource = defaultdict(list)
    components_by_revision = defaultdict(list)
    history_by_resource = defaultdict(list)
    for node in nodes.values():
        ntype = node["type"]
        if ntype == "CTV":
            rid = nodes[node["work_id"]]["resource_id"]
            ctvs_by_resource[rid].append(node)
        elif ntype == "DocumentaryComponent":
            components_by_revision[node["revision_id"]].append(node)
        elif ntype == "EditorialReview":
            history_by_resource[node["resource_id"]].append(node)
    entry = {
        "graph": graph,
        "nodes": nodes,
        "outgoing": outgoing,
        "parents": parents,
        "ctv_parents": ctv_parents,
        "derived": derived,
        "eligible": eligible,
        "summaries": summaries,
        "summaries_by_id": summaries_by_id,
        "ctvs_by_resource": ctvs_by_resource,
        "components_by_revision": components_by_revision,
        "history_by_resource": history_by_resource,
    }
    with _REVIEW_INDEX_LOCK:
        if len(_REVIEW_INDEX_CACHE) >= _MAX_REVIEW_INDEX_CACHE:
            _REVIEW_INDEX_CACHE.clear()
        _REVIEW_INDEX_CACHE[key] = entry
    return entry


def snapshot(db):
    return {
        "nodes": [{"id": i, "type": k, **json.loads(p)} for i, k, p in db.execute("SELECT id,kind,payload FROM sat_nodes")],
        "edges": [{"id": i, "source": s, "type": k, "target": t, "evidence": json.loads(p)}
                  for i, s, k, t, p in db.execute("SELECT id,source,predicate,target,payload FROM sat_edges")],
    }


def documents(graph):
    return [dict(item) for item in _review_index(graph)["summaries"]]


def _document_summaries(nodes, eligible):
    docs = {}
    for v in nodes.values():
        if v["type"] != "CTV" or v.get("editorial_superseded_by"):
            continue
        w = nodes[v["work_id"]]
        rid = w["resource_id"]
        doc = docs.setdefault(rid, {"id": rid, "title": nodes[rid].get("title", rid),
                                   "components": set(), "versions": 0, "retrievable": 0, "revisions": set()})
        doc["components"].add(w["id"])
        doc["versions"] += 1
        doc["retrievable"] += v["id"] in eligible
        if v.get("documentary_revision"):
            doc["revisions"].add(v["documentary_revision"])
    return [{**d, "components": len(d["components"]), "revisions": sorted(d["revisions"])}
            for d in sorted(docs.values(), key=lambda d: d["title"])]


def document(graph, resource_id, *, include_texts: bool = True):
    idx = _review_index(graph)
    nodes = idx["nodes"]
    active = idx["eligible"]
    info = idx["summaries_by_id"].get(resource_id)
    if info is None:
        raise ValueError("Documento no encontrado en el corpus SAT")
    revisions = [nodes[r] for r in info["revisions"] if not nodes[r].get("editorial_superseded_by")]
    editable = len(revisions) == 1
    revision = revisions[0] if editable else None
    parents = idx["parents"]
    derived = idx["derived"]
    outgoing = idx["outgoing"]
    versions = []
    for v in idx["ctvs_by_resource"].get(resource_id, ()):
        w = nodes[v["work_id"]]
        texts = [nodes[t] for t in outgoing.get((v["id"], "has_text"), ())]
        version_texts = (
            [{"id": t["id"], "language": t["language"], "text": t["text"]} for t in texts]
            if include_texts
            else [{"id": t["id"], "language": t["language"]} for t in texts]
        )
        versions.append({"id": v["id"], "work_id": w["id"], "component_id": derived.get(v["id"]),
                         "label": w["label"], "kind": w.get("kind"), "retrievable": v["id"] in active,
                         "archived": bool(v.get("editorial_superseded_by")),
                         "provenance": v.get("provenance_state"), "date": v.get("snapshot_as_of") or v.get("valid_from"),
                         "texts": version_texts})
    components = []
    if revision:
        for n in idx["components_by_revision"].get(revision["id"], ()):
            components.append({"id": n["id"], "label": n["label"], "kind": n["kind"],
                               "start": n["start"], "end": n["end"], "parent_id": parents.get(n["id"])})
        attached = [v for v in versions if not v["archived"]]
        if components:
            # Editing only supported for a complete one-to-one documentary edition.
            editable = (len(attached) == len(components)
                        and {v["component_id"] for v in attached} == {n["id"] for n in components}
                        and all(len(v["texts"]) == 1 and v["texts"][0]["language"] == "es" for v in attached))
        elif attached:
            # Compacted snapshots omit DocumentaryComponent audit nodes; project a
            # read-only hierarchy directly from active CTVs and contains_version edges.
            editable = False
            ctv_parents = idx["ctv_parents"]
            attached_ids = {v["id"] for v in attached}
            for v in attached:
                ctv_node = nodes[v["id"]]
                v["component_id"] = v["id"]
                parent_id = ctv_parents.get(v["id"])
                components.append({
                    "id": v["id"],
                    "label": v["label"],
                    "kind": v["kind"],
                    "start": ctv_node.get("start") or 0,
                    "end": ctv_node.get("end") or 0,
                    "parent_id": parent_id if parent_id in attached_ids else None,
                })
        else:
            editable = False
    history = idx["history_by_resource"].get(resource_id, ())
    return {**info, "editable": editable, "versions": versions,
            "edition": {"revision": revision["id"], "markdown": revision["markdown"],
                        "components": sorted(components, key=lambda n: (n["start"], -n["end"], n["id"]))} if revision else None,
            "directory": revision.get("directory") if revision else None,
            "candidate_pdf": revision.get("candidate_pdf") if revision else None,
            "origin_candidate": revision.get("origin_candidate") if revision else None,
            "evidence_id": revision.get("evidence_id") if revision else None,
            "history": [{k: v for k, v in h.items() if k != "previous_edition"}
                        for h in sorted(history, key=lambda n: n["recorded_at"], reverse=True)]}


class CorpusEditor:
    def __init__(self, store: SATGraphStore):
        self.store = store

    def list(self):
        return documents(self.store.export())

    def get(self, resource_id, *, include_texts: bool = True):
        return document(self.store.export(), resource_id, include_texts=include_texts)

    def revision_meta(self, resource_id):
        """Fast metadata lookup for PDF/Markdown routes without full document assembly."""
        getter = getattr(self.store, "document_revision_meta", None)
        if callable(getter):
            meta = getter(resource_id)
            if meta is None:
                raise ValueError("Documento no encontrado en el corpus SAT")
            return meta
        return self.get(resource_id, include_texts=False)

    def apply(self, resource_id, publication, actor, *, candidate=None, official=None):
        edition = validate_edition(publication.edition)
        if not publication.reason.strip():
            raise ValueError("Indique el motivo de la corrección")
        if official and (candidate or official.resource["id"] != resource_id or
                         official.resource["kind"] != "norm" or official.evidence.markdown_sha256 != digest(edition.markdown)):
            raise ValueError("La edición oficial no corresponde a la evidencia registrada")
        with self.store._transaction() as db:
            graph = snapshot(db)
            by_id = {n["id"]: n for n in graph["nodes"]}
            if official:
                # La revisión documental retiene el PDF anterior y sus CTV
                # archivadas. La nueva evidencia no modifica el Resource legal.
                if resource_id not in by_id:
                    by_id[resource_id] = {k: v for k, v in official.resource.items() if k != "id"}
                    self.store._node(db, resource_id, "Resource", by_id[resource_id])
                exists = any(n["type"] == "Work" and n.get("resource_id") == resource_id for n in graph["nodes"])
                current = document(graph, resource_id) if exists else {
                    "editable": True, "edition": {"revision": "new:official-source", "components": []}, "versions": []}
                old_rev = by_id.get(edition.revision)
                self.store._node(db, official.evidence.evidence_id, "Source", asdict(official.evidence))
            elif candidate:
                if any(candidate_already_published(candidate, n) for n in by_id.values()):
                    raise Conflict("Este candidato ya fue publicado. Edítelo desde el corpus publicado.")
                candidate_resource = by_id.get(candidate.get("official_id"), {})
                existing = any(n["type"]=="Work" and n.get("resource_id")==candidate_resource.get("id")
                               for n in by_id.values())
                # Never overwrite an existing norm with an annex or another extraction.
                archive_only = existing or candidate_resource.get("kind")!="norm" or candidate["reference_only"]
                resource_id = candidate["id"].replace("candidate:", "local:documentary:", 1) if archive_only else candidate_resource["id"]
                if archive_only:
                    by_id[resource_id] = {"title": candidate["title"], "url": candidate["source_url"] or candidate_resource.get("url"),
                                          "kind": "documentary_reference"}
                    self.store._node(db, resource_id, "Resource", by_id[resource_id])
                if candidate["evidence_id"] not in by_id:
                    self.store._node(db, candidate["evidence_id"], "Source", candidate["source"])
                current = candidate
                old_rev = {"evidence_id": candidate["evidence_id"], "candidate_pdf": candidate["pdf_name"],
                           "origin_candidate": candidate["id"], "source_markdown_sha256": candidate["source"]["markdown_sha256"]}
            else:
                current = document(graph, resource_id)
                old_rev = by_id.get(edition.revision)
            if not current["editable"]:
                raise ValueError("Este documento requiere resolver sus versiones antes de editarlo")
            if current["edition"]["revision"] != edition.revision:
                raise Conflict("El corpus cambió desde que lo abrió. Recargue antes de aplicar; su borrador no se ha sobrescrito.")
            if not candidate and current["edition"] == edition.model_dump():
                raise ValueError("No hay cambios para aplicar")
            old_components = {n["id"]: n for n in current["edition"]["components"]}
            for n in edition.components:
                if n.id not in old_components and not n.id.startswith("new:"):
                    raise ValueError("Identidad de componente ajena al documento")
            rev_id = "documentary-revision:" + digest(canonical(edition.model_dump()))
            review_id = "editorial-review:" + str(uuid.uuid4())
            audit = {"rule": "official-document-editor-v1" if official else "human-corpus-editor-v1", "review_id": review_id,
                     "reviewer": actor, "recorded_at": datetime.now(timezone.utc).isoformat()}
            rev_payload = {k: v for k, v in (old_rev or {}).items() if k not in {"id", "type", "editorial_superseded_by"}}
            if official:
                rev_payload.update(directory=None, origin_candidate=None, candidate_pdf=official.pdf_name,
                                   evidence_id=official.evidence.evidence_id, source_url=official.url,
                                   official_edition_as_of=official.edition_as_of.isoformat(),
                                   source_markdown_sha256=official.evidence.markdown_sha256)
            rev_payload.update(markdown=edition.markdown, markdown_sha256=digest(edition.markdown),
                               review_hash=review_id, previous_revision=edition.revision, **audit)
            self.store._node(db, rev_id, "DocumentaryRevision", rev_payload)
            old_versions = {v["component_id"]: by_id[v["id"]] for v in current["versions"] if not v["archived"]}
            if official:
                exemplar = {"scope": "PE", "valid_from": None, "valid_to": None, "checked_through": None,
                            "snapshot_as_of": official.edition_as_of.isoformat(),
                            "provenance_state": "official_document_snapshot"}
            else:
                exemplar = next(iter(old_versions.values()), {
                    "scope": "PE", "valid_from": None, "valid_to": None, "checked_through": None,
                    "snapshot_as_of": None, "provenance_state": "documentary_reference"
                    if candidate and archive_only else "user_attested_snapshot",
                })
            mapping = {}
            amendments = dict(official.amendments) if official else {}
            for n in edition.components:
                old = old_versions.get(n.id)
                source_id = by_id[n.id]["source_node_id"] if not candidate and n.id in old_components else n.id
                wid = old["work_id"] if old else work_id(resource_id, "editorial-" + digest(source_id))
                cid = "documentary-component:" + digest(canonical([rev_id, source_id]))
                text = edition.markdown[n.start:n.end]
                vid = "ctv-editorial:" + digest(canonical([rev_id, wid, digest(text)]))
                tid = "clv-editorial:" + digest(canonical([vid, "es", digest(text)]))
                span_audit = {**audit, "start": n.start, "end": n.end, "text_sha256": digest(text),
                              "documentary_revision": rev_id, "evidence_id": rev_payload["evidence_id"],
                              "source_url": rev_payload.get("source_url", by_id[resource_id]["url"])}
                self.store._node(db, cid, "DocumentaryComponent", {
                    "revision_id": rev_id, "source_node_id": source_id, "kind": n.kind, "label": n.label,
                    **span_audit, "provenance_state": "user_approved_documentary"})
                work = ({k: v for k, v in by_id[wid].items() if k not in {"id", "type"}}
                        if old else {"resource_id": resource_id, "component": "editorial-" + digest(source_id)})
                work.update(label=n.label, kind=n.kind)
                db.execute("INSERT INTO sat_nodes VALUES (?, 'Work', ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload", (wid, canonical(work)))
                payload = {k: v for k, v in (old or exemplar).items() if k not in {"id", "type", "editorial_superseded_by"}}
                if modifier := amendments.get(n.id):
                    legal_source = self.store._get(db, modifier, "Resource")
                    payload["amending_source"] = {"id": modifier, "title": legal_source["title"], "url": legal_source["url"]}
                payload.update(work_id=wid, **span_audit)
                self.store._node(db, vid, "CTV", payload)
                self.store._node(db, tid, "CLV", {"language": "es", "text": text, **span_audit})
                if amending_source := payload.get("amending_source"):
                    self.store._edge(db, vid, "amended_by", amending_source["id"], span_audit)
                for s, p, t in ((cid, "part_of_revision", rev_id), (vid, "version_of", wid),
                                (vid, "has_text", tid), (tid, "evidenced_by", rev_payload["evidence_id"]),
                                (vid, "derived_from_documentary", cid), (wid, "instrument", resource_id)):
                    self.store._edge(db, s, p, t, audit)
                mapping[n.id] = (cid, wid, vid)
            # Work topology is current editorial topology; old CTV topology stays
            # attached to archived versions for audit, never mixed into retrieval.
            for v in old_versions.values():
                db.execute("DELETE FROM sat_edges WHERE predicate='has_part' AND (source=? OR target=?)", (v["work_id"], v["work_id"]))
            for n in edition.components:
                if n.parent_id:
                    pc, pw, pv = mapping[n.parent_id]
                    cc, cw, cv = mapping[n.id]
                    for s, p, t in ((pc, "documentary_has_part", cc), (pw, "has_part", cw), (pv, "contains_version", cv)):
                        self.store._edge(db, s, p, t, audit)
            for old in ([] if candidate or old_rev is None else [old_rev, *old_versions.values()]):
                payload = {k: v for k, v in old.items() if k not in {"id", "type"}}
                payload["editorial_superseded_by"] = rev_id
                db.execute("UPDATE sat_nodes SET payload=? WHERE id=?", (canonical(payload), old["id"]))
            if official:
                # Dejar la fuente de la cita disponible para lectura exacta e
                # histórica, pero no reutilizar la cita antigua como regla actual.
                for identity in official.historical_quotations:
                    payload = self.store._get(db, identity, "CTV")
                    payload["historical_quotation"] = {"source": resource_id, "review": review_id}
                    db.execute("UPDATE sat_nodes SET payload=? WHERE id=?", (canonical(payload), identity))
            self.store._node(db, review_id, "EditorialReview", {**audit, "resource_id": resource_id,
                "reason": publication.reason, "previous_revision": edition.revision, "revision": rev_id,
                "component_count": len(edition.components), "previous_edition": current["edition"]})
            self.store._reject_cycles(db, "has_part")
            self.store._reject_cycles(db, "contains_version")
            result = document(snapshot(db), resource_id)
        return result


def candidate_already_published(item, node):
    return node["type"] == "DocumentaryRevision" and (
        node.get("origin_candidate") == item["id"]
        or (item.get("evidence_id", "").startswith("pdf-sha256-")
            and node.get("evidence_id") == item["evidence_id"]))


class CandidateShelf:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.store = SurrealSATGraphStore(candidates=True)

    def list(self):
        if not self.store.candidate_store_available():
            return []
        sources = {}
        for name in ("acquisition.json", "attachments.json"):
            path = self.root / name
            if path.is_file():
                for item in _cached_json(path):
                    if item.get("sha256"):
                        sources[item["sha256"]] = item
        if hasattr(self.store, "list_candidate_parses"):
            evidence = self.store.list_candidate_parses()
        else:
            with self.store._reader() as db:
                evidence = {eid: pid for eid, pid in db.execute(
                    "SELECT evidence_id,min(id) FROM sat_parses GROUP BY evidence_id HAVING count(*)=1")}
        result = []
        for path in sorted(self.root.glob("converted/*/report.json")):
            report = _cached_json(path)
            sha = report.get("pdf_sha256")
            eid = f"pdf-sha256-{sha}"
            if eid not in evidence:
                continue
            source = sources.get(sha, {})
            name = path.parent.name
            result.append({"id": f"candidate:{name}", "title": name, "candidate": True,
                           "evidence_id": eid, "parse_id": evidence[eid],
                           "official_id": source.get("id") or ("pe:ley:30364" if name=="ley-30364-original" else None),
                           "source_url": source.get("url"),
                           "reference_only": name in {"pe-dl-295", "pe-ley-27337-attachment-2"},
                           "pdf_name": Path(source.get("path") or report["pdf"]).name})
        return result

    def get(self, identity):
        item = next((row for row in self.list() if row["id"] == identity), None)
        if not item:
            raise ValueError("Candidato inexistente")
        if hasattr(self.store, "get_candidate_evidence"):
            row = self.store.get_candidate_evidence(item["parse_id"], item["evidence_id"])
        else:
            with self.store._reader() as db:
                row = db.execute(
                    """SELECT d.markdown,p.artifact,n.payload,s.payload FROM sat_parses p
                       JOIN sat_documents d ON d.evidence_id=p.evidence_id
                       JOIN sat_nodes n ON n.id=p.id JOIN sat_nodes s ON s.id=d.evidence_id
                       WHERE p.id=? AND p.evidence_id=?""", (item["parse_id"], item["evidence_id"])).fetchone()
        if not row:
            raise ValueError("Evidencia candidata inexistente")
        markdown, raw, parse, source = row
        if digest(raw) != json.loads(parse)["artifact_sha256"] or digest(markdown) != json.loads(source)["markdown_sha256"]:
            raise ValueError("La evidencia candidata no coincide con sus hashes")
        structure = json.loads(raw)["structure"]
        edition = validate_edition(Edition(revision=item["parse_id"], markdown=markdown, components=[
            {k: n[k] for k in ("id", "label", "kind", "parent_id", "start", "end")}
            for n in structure["nodes"]]))
        return {**item, "components": len(edition.components), "retrievable": 0, "revisions": [],
                "versions": [], "history": [], "editable": True, "edition": edition.model_dump(),
                "directory": None, "source": json.loads(source), "diagnostics": len(structure["diagnostics"])}

    def pdf_path(self, item):
        directory = (self.root / "pdf").resolve()
        path = (directory / item["pdf_name"]).resolve()
        if not path.is_relative_to(directory) or not path.is_file() or "pdf-sha256-" + cached_file_sha256(path) != item["evidence_id"]:
            raise ValueError("El PDF local no coincide con la evidencia candidata")
        return path
