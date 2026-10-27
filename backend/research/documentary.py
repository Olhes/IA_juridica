"""Ediciones PDF revisadas por IA: investigación, nunca vigencia jurídica SAT.

Verifica artefactos locales; una URL declarada no es una firma del editor estatal.
No descarga archivos, crea ReviewManifest ni escribe en el almacén canónico.
"""

from datetime import date, datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from retrieval.sat import SATRetriever, fingerprint

OFFICIAL_HOSTS = {
    "www3.congreso.gob.pe",
    "repositorio.mimp.gob.pe",
    "apps.contraloria.gob.pe",
    "busquedas.elperuano.pe",
}
HASH = r"^[a-f0-9]{64}$"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Artifact(Contract):
    path: Path
    sha256: str = Field(pattern=HASH)

    def read(self):
        content = self.path.read_bytes()
        if sha256(content).hexdigest() != self.sha256:
            raise ValueError(f"Artefacto divergente: {self.path.name}")
        return content


class ParagraphCorrection(Contract):
    text_ref: str = Field(pattern=r"^#/texts/[0-9]+$")
    text_sha256: str = Field(pattern=HASH)
    reason: str = Field(min_length=1)


class DocumentarySource(Contract):
    id: str = Field(pattern=r"^pdf-sha256-[a-f0-9]{64}$")
    source_url: str
    pdf: Artifact
    markdown: Artifact
    docling_json: Artifact
    raw_docling_json: Artifact | None = None
    paragraph_corrections: list[ParagraphCorrection] = Field(default_factory=list)
    selected_pdf_pages: list[StrictInt] = Field(min_length=1)
    published_on: date | None = None

    @model_validator(mode="after")
    def official(self):
        url = urlsplit(self.source_url)
        if (
            url.scheme != "https"
            or url.hostname not in OFFICIAL_HOSTS
            or url.username
            or url.password
            or url.port not in (None, 443)
        ):
            raise ValueError("Fuente PDF fuera del catálogo oficial experimental")
        if self.id != "pdf-sha256-" + self.pdf.sha256:
            raise ValueError("Identidad PDF incoherente")
        return self


class DocumentaryUnit(Contract):
    source_id: str
    resource_id: str = Field(pattern=r"^pe:[a-z0-9][a-z0-9:-]*$")
    resource_title: str = Field(min_length=1)
    component: str = Field(pattern=r"^[a-z0-9][a-z0-9/-]*$")
    label: str = Field(min_length=1)
    start: int = Field(ge=0, strict=True)
    end: int = Field(gt=0, strict=True)
    text_sha256: str = Field(pattern=HASH)
    pdf_pages: list[StrictInt] = Field(min_length=1)
    reason: str = Field(min_length=1)
    kind: Literal["article", "numeral", "inciso", "subinciso"] = "article"
    parent_component: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9/-]*$")

    @model_validator(mode="after")
    def structural_identity(self):
        if (self.kind == "article") != (self.parent_component is None):
            raise ValueError(
                "Artículo raíz o componente subordinado con padre requerido"
            )
        if self.parent_component is not None and not self.component.startswith(
            self.parent_component + "/"
        ):
            raise ValueError("Componente fuera de la ruta del padre")
        return self


class DocumentaryBundle(Contract):
    schema_version: Literal[1] = 1
    review_kind: Literal["ai_documentary"]
    reviewer: str = Field(min_length=1)
    reviewed_at: datetime
    sources: list[DocumentarySource] = Field(min_length=1)
    units: list[DocumentaryUnit] = Field(min_length=1)

    @model_validator(mode="after")
    def documentary_only(self):
        if not self.reviewer.strip() or self.reviewed_at.utcoffset() is None:
            raise ValueError("Revisor y fecha con zona requeridos")
        if len({s.id for s in self.sources}) != len(self.sources):
            raise ValueError("Fuente duplicada")
        return self


def build_snapshot(raw_bundle):
    """Revalida PDF, exportación Docling y cada selección exacta; sin fechas legales."""
    import json

    from docling_core.types.doc import DoclingDocument
    from pypdf import PdfReader

    bundle = DocumentaryBundle.model_validate(raw_bundle)
    sources, markdowns = {}, {}
    nodes, edges = [], []
    review_payload = bundle.model_dump(mode="json")
    # Defaults nuevos no alteran hashes/snapshots de bundles v1 congelados.
    for unit in review_payload["units"]:
        if unit["parent_component"] is None:
            unit.pop("parent_component")
            unit.pop("kind")
    review_id = "documentary-review:" + fingerprint(review_payload)
    for source in bundle.sources:
        pdf_bytes = source.pdf.read()
        if not pdf_bytes.startswith(b"%PDF-"):
            raise ValueError("El original no es PDF")
        page_count = len(PdfReader(BytesIO(pdf_bytes)).pages)
        pages = source.selected_pdf_pages
        if len(set(pages)) != len(pages) or any(
            type(p) is not int or p < 1 or p > page_count for p in pages
        ):
            raise ValueError("Selección de páginas inválida")
        markdown = source.markdown.read().decode("utf-8")
        if "\ufffd" in markdown:
            raise ValueError("Extracción con caracteres de reemplazo")
        layout_json = json.loads(source.docling_json.read())
        if source.paragraph_corrections:
            if source.raw_docling_json is None:
                raise ValueError("Corrección sin artefacto Docling original")
            original = json.loads(source.raw_docling_json.read())
            DoclingDocument.model_validate(original)
            refs = set()
            for correction in source.paragraph_corrections:
                index = int(correction.text_ref.rsplit("/", 1)[1])
                if index >= len(original["texts"]):
                    raise ValueError("Referencia Docling inexistente")
                item = original["texts"][index]
                if (
                    correction.text_ref in refs
                    or item["self_ref"] != correction.text_ref
                    or item["label"] != "list_item"
                    or item.get("marker") != ""
                    or item.get("enumerated") is not False
                    or sha256(item["text"].encode()).hexdigest()
                    != correction.text_sha256
                    or not correction.reason.strip()
                ):
                    raise ValueError("Reclasificación documental inválida")
                refs.add(correction.text_ref)
                item["label"] = "text"
                item.pop("marker")
                item.pop("enumerated")
            if original != layout_json:
                raise ValueError(
                    "Corrección alteró algo más que la clasificación permitida"
                )
        elif source.raw_docling_json is not None:
            raise ValueError("Artefacto original sin correcciones declaradas")
        layout = DoclingDocument.model_validate(layout_json)
        if layout.export_to_markdown() != markdown:
            raise ValueError("Markdown no corresponde a exportación Docling")
        sources[source.id], markdowns[source.id] = source, markdown
        nodes.append(
            {
                "id": source.id,
                "type": "Source",
                "source_url": source.source_url,
                "pdf_sha256": source.pdf.sha256,
                "markdown_sha256": source.markdown.sha256,
                "selected_pdf_pages": pages,
                "published_on": (
                    str(source.published_on) if source.published_on else None
                ),
                "provenance_state": "ai_documentary",
            }
        )
    by_id = {n["id"]: n for n in nodes}
    seen, used_sources = set(), set()
    units_by_key, versions_by_key = {}, {}
    for unit in bundle.units:
        if unit.source_id not in sources:
            raise ValueError("Unidad sin fuente")
        source, markdown = sources[unit.source_id], markdowns[unit.source_id]
        text = markdown[unit.start : unit.end]
        if (
            unit.end <= unit.start
            or unit.end > len(markdown)
            or not text.strip()
            or sha256(text.encode()).hexdigest() != unit.text_sha256
            or not unit.reason.strip()
            or not unit.label.strip()
            or not unit.resource_title.strip()
            or not set(unit.pdf_pages) <= set(source.selected_pdf_pages)
            or any(type(p) is not int for p in unit.pdf_pages)
        ):
            raise ValueError("Selección documental inválida")
        key = (unit.source_id, unit.resource_id, unit.component)
        if key in seen:
            raise ValueError("Componente duplicado en la misma edición")
        seen.add(key)
        units_by_key[key] = unit
        used_sources.add(unit.source_id)
        resource = {
            "id": unit.resource_id,
            "type": "Resource",
            "title": unit.resource_title,
        }
        wid = "documentary-work:" + fingerprint([unit.resource_id, unit.component])
        work = {
            "id": wid,
            "type": "Work",
            "resource_id": unit.resource_id,
            "component": unit.component,
            "label": unit.label,
        }
        if unit.parent_component is not None:
            work.update(
                kind=unit.kind,
                parent_work_id="documentary-work:"
                + fingerprint([unit.resource_id, unit.parent_component]),
            )
        for node in (resource, work):
            if node["id"] in by_id and by_id[node["id"]] != node:
                raise ValueError("Metadatos de Work/Resource contradictorios")
            if node["id"] not in by_id:
                by_id[node["id"]] = node
                nodes.append(node)
        vid = "dv:" + fingerprint([*key, unit.start, unit.end, unit.text_sha256])
        versions_by_key[key] = vid
        tid = "documentary-text:" + vid
        audit = {
            "evidence_id": source.id,
            "source_url": source.source_url,
            "review_id": review_id,
            "provenance_state": "ai_documentary",
        }
        nodes.extend(
            [
                {"id": vid, "type": "DocumentaryVersion", "work_id": wid, **audit},
                {
                    "id": tid,
                    "type": "DocumentaryText",
                    "text": text,
                    "start": unit.start,
                    "end": unit.end,
                    "text_sha256": unit.text_sha256,
                    "pdf_pages": unit.pdf_pages,
                    "language": "es",
                    "review_reason": unit.reason,
                    **audit,
                },
            ]
        )
        edges.extend(
            [
                {"source": vid, "type": "has_text", "target": tid},
                {"source": vid, "type": "source", "target": source.id},
                {"source": wid, "type": "has_documentary_edition", "target": vid},
            ]
        )
    children = {}
    hierarchy = {
        "article": {"numeral", "inciso"},
        "numeral": {"numeral", "inciso"},
        "inciso": {"numeral", "subinciso"},
        "subinciso": {"numeral"},
    }
    for key, unit in units_by_key.items():
        if unit.parent_component is None:
            continue
        parent_key = (unit.source_id, unit.resource_id, unit.parent_component)
        parent = units_by_key.get(parent_key)
        if parent is None or not (
            parent.start <= unit.start < unit.end <= parent.end
            and (parent.start, parent.end) != (unit.start, unit.end)
            and set(unit.pdf_pages) <= set(parent.pdf_pages)
            and unit.kind in hierarchy[parent.kind]
        ):
            raise ValueError(
                "Membresía documental sin padre/contención/jerarquía verificable"
            )
        children.setdefault(parent_key, []).append(unit)
        edges.append(
            {
                "source": versions_by_key[parent_key],
                "type": "contains_version",
                "target": versions_by_key[key],
            }
        )
    for siblings in children.values():
        ordered = sorted(siblings, key=lambda unit: unit.start)
        if any(a.end > b.start for a, b in zip(ordered, ordered[1:])):
            raise ValueError("Componentes hermanos superpuestos")
    if used_sources != set(sources):
        raise ValueError("Fuente sin unidades revisadas")
    return {"nodes": nodes, "edges": edges}


class DocumentaryPlan(Contract):
    """Selecciona bytes/edición, no derecho vigente a una fecha."""

    query: str = Field(min_length=1, max_length=4000)
    source_ids: list[str] = Field(min_length=1, max_length=50)
    resource_ids: list[str] = Field(default_factory=list, max_length=50)
    component: str | None = Field(default=None, max_length=200)
    strategy: Literal["bm25", "metadata", "hybrid", "ppr", "tree"] = "metadata"
    top_k: int = Field(default=5, ge=1, le=20)
    candidates: int = Field(default=30, ge=1, le=100)
    chunk_chars: int = Field(default=1000, ge=100, le=4000)
    chunk_policy: Literal["fixed", "paragraph"] = "fixed"
    membership_policy: Literal["verified", "disabled"] = "verified"
    context_bytes: int = Field(default=16000, ge=100, le=64000)

    @property
    def as_of(self):
        # Solo compatibilidad con el motor de ranking; no se publica una fecha ficticia.
        return "not_applicable_documentary_edition"

    @model_validator(mode="after")
    def coherent(self):
        if not self.query.strip() or self.top_k > self.candidates:
            raise ValueError("Consulta/presupuesto inválido")
        if self.component is not None and len(self.resource_ids) != 1:
            raise ValueError("Componente requiere norma inequívoca")
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("Edición duplicada")
        return self


def documentary_windows(text, limit, policy="fixed"):
    """Partición exacta sin overlap; prioriza límites naturales, con fallback acotado."""
    if limit < 1 or policy not in {"fixed", "paragraph"}:
        raise ValueError("Política de segmentación inválida")
    start = 0
    while start < len(text):
        end = min(len(text), start + limit)
        if policy == "paragraph" and end < len(text):
            # No crear un microchunk solo por un encabezado inicial. Las ventanas
            # resultantes siguen acotadas y conservan también todo whitespace.
            for pattern in (r"\r?\n\r?\n", r"\r?\n", r"(?<=[.!?])\s+", r"\s+"):
                boundaries = [
                    start + match.end()
                    for match in re.finditer(pattern, text[start:end])
                    if match.end() >= max(1, limit // 2)
                ]
                if boundaries:
                    end = boundaries[-1]
                    break
        yield start, end
        start = end


class DocumentaryRetriever(SATRetriever):
    """Reutiliza ranking SAT, sin abrir la elegibilidad del retriever público."""

    def eligible(self, plan):
        if not isinstance(plan, DocumentaryPlan):
            raise ValueError("Plan documental requerido; no admite as_of normativo")
        result = []
        for version in self.nodes.values():
            if (
                version["type"] != "DocumentaryVersion"
                or version.get("provenance_state") != "ai_documentary"
                or version["evidence_id"] not in plan.source_ids
            ):
                continue
            work = self.nodes[version["work_id"]]
            if plan.resource_ids and work["resource_id"] not in plan.resource_ids:
                continue
            if plan.component is not None and work["component"] != plan.component:
                continue
            texts = self._texts(version, "es")
            if len(texts) == 1:
                result.append({"version": version, "work": work, "text": texts[0]})
        return sorted(result, key=lambda item: item["version"]["id"])

    def chunks(self, plan):
        result = []
        for item in self.eligible(plan):
            version, work, text = item["version"], item["work"], item["text"]
            for start, end in documentary_windows(
                text["text"], plan.chunk_chars, plan.chunk_policy
            ):
                content = text["text"][start:end]
                result.append(
                    {
                        "id": "documentary-tu:"
                        + fingerprint([version["id"], text["id"], start, end]),
                        "version_id": version["id"],
                        "text_id": text["id"],
                        "work_id": work["id"],
                        "resource_id": work["resource_id"],
                        "resource_label": self.nodes[work["resource_id"]]["title"],
                        "component": work["component"],
                        "label": work["label"],
                        "content": content,
                        "start": text["start"] + start,
                        "end": text["start"] + end,
                        "text_sha256": sha256(content.encode()).hexdigest(),
                        "evidence_id": version["evidence_id"],
                        "source_url": version["source_url"],
                        "review_id": version["review_id"],
                        "pdf_pages": text["pdf_pages"],
                        "provenance_state": "ai_documentary",
                        "chunk_policy": plan.chunk_policy,
                    }
                )
        return result

    def search(self, plan, *, provider=None, stages=None):
        result = super().search(plan, provider=provider, stages=stages)
        result.pop("as_of")
        result.update(
            engine="official_pdf_documentary_research",
            source_ids=plan.source_ids,
            warning="Revisión documental IA de ediciones seleccionadas; no vigencia ni gold jurídico experto.",
        )
        return result


def validate_documentary_dataset(dataset):
    expected = build_snapshot(dataset["documentary_bundle"])
    if fingerprint(expected) != fingerprint(dataset["snapshot"]):
        raise ValueError("Snapshot no corresponde a artefactos documentales revisados")


def documentary_root_map(snapshot):
    """Identidad de evaluación, no enriquecimiento de contexto ni expansión de filtros."""
    versions = {
        n["id"]: n for n in snapshot["nodes"] if n["type"] == "DocumentaryVersion"
    }
    parents = {}
    for edge in snapshot["edges"]:
        if edge["type"] != "contains_version":
            continue
        child, parent = edge["target"], edge["source"]
        if (
            child in parents
            or child not in versions
            or parent not in versions
            or versions[child]["evidence_id"] != versions[parent]["evidence_id"]
        ):
            raise ValueError("Membresías ambiguas o entre ediciones")
        parents[child] = parent
    roots = {}
    for identity in versions:
        current, visited = identity, set()
        while current in parents:
            if current in visited:
                raise ValueError("Ciclo de membresías")
            visited.add(current)
            current = parents[current]
        roots[identity] = current
    return roots


def validate_references(snapshot, case):
    """Cada gold documental debe estar respaldado por un span exacto, no un resumen."""
    nodes = {n["id"]: n for n in snapshot["nodes"]}
    texts = {
        edge["source"]: nodes[edge["target"]]
        for edge in snapshot["edges"]
        if edge["type"] == "has_text"
    }
    references = case.get("reference_spans", [])
    if {r["version_id"] for r in references} != set(case["expected_version_ids"]):
        raise ValueError("Gold documental requiere referencias para cada edición")
    for ref in references:
        text = texts[ref["version_id"]]
        start, end = ref["start"], ref["end"]
        if (
            type(start) is not int
            or type(end) is not int
            or not text["start"] <= start < end <= text["end"]
            or sha256(
                text["text"][start - text["start"] : end - text["start"]].encode()
            ).hexdigest()
            != ref["text_sha256"]
        ):
            raise ValueError("Referencia documental divergente")
