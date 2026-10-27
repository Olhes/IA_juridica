"""SAT-Graph mínimo y persistente, aislado del grafo probabilístico de LightRAG.

Work/CTV/CLV corresponden a Item/Version/TextUnit en la API pública SAT.
No interpreta reformas ni vigencia: solo aplica manifiestos jurídicos revisados.
"""

from contextlib import closing, contextmanager
from dataclasses import asdict
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from ingestion.source_evidence import SourceEvidence
from ingestion.legal_structure import parse_legal_structure
from .catalog import load_catalog
from .contracts import ReviewManifest, ReviewedUnit, Span


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def work_id(resource_id: str, component: str) -> str:
    return f"work:{resource_id}/{component}"


def version_id(unit: ReviewedUnit) -> str:
    # No contiene valid_to: cerrar una versión no cambia su identidad histórica.
    return f"ctv:{digest(canonical([work_id(unit.resource_id, unit.component), unit.scope, str(unit.valid_from), unit.text_sha256]))}"


def candidate_spans(markdown: str) -> list[dict]:
    """Separar artículos sin overlap ni truncamiento; el OCR puede requerir corrección.

    El preámbulo y el texto sin artículos también se conservan. No deducir una
    jerarquía jurídica de los niveles Markdown ni de la numeración encontrada.
    """
    headings = list(
        re.finditer(
            r"(?im)^[ \t]*(?:#{1,6}[ \t]+)?Art[ií]culo[ \t]+(?:\d+[a-zA-Z-]*|[uú]nico)\b[^\n]*",
            markdown,
        )
    )
    starts = sorted({0, *(match.start() for match in headings)})
    return [
        {
            "start": start,
            "end": end,
            "text_sha256": digest(markdown[start:end]),
            "label": (
                markdown[start:end].splitlines()[0][:160] if markdown[start:end] else ""
            ),
        }
        for start, end in zip(starts, [*starts[1:], len(markdown)])
        if end > start
    ]


def stage_document(
    path: Path,
    evidence: SourceEvidence,
    markdown: str,
    docling_document: dict | None = None,
) -> dict:
    """Punto común de upload/batch; inicializar almacenamiento solo tras evidencia."""
    return SATGraphStore(path).stage(evidence, markdown, docling_document)


class SATGraphStore:
    """Una transacción por documento/revisión, conexiones cortas, sin servicios externos."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as db:
            db.execute("CREATE TABLE IF NOT EXISTS sat_meta (version INTEGER NOT NULL)")
            if not db.execute("SELECT version FROM sat_meta").fetchone():
                db.execute("INSERT INTO sat_meta VALUES (1)")
            if db.execute("SELECT version FROM sat_meta").fetchall() != [(1,)]:
                raise ValueError("Esquema SAT no soportado")
            db.execute(
                "CREATE TABLE IF NOT EXISTS sat_nodes (id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL)"
            )
            db.execute("CREATE INDEX IF NOT EXISTS sat_node_kind ON sat_nodes(kind)")
            db.execute(
                "CREATE TABLE IF NOT EXISTS sat_edges (id TEXT PRIMARY KEY, source TEXT NOT NULL REFERENCES sat_nodes(id), predicate TEXT NOT NULL, target TEXT NOT NULL REFERENCES sat_nodes(id), payload TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS sat_documents (evidence_id TEXT PRIMARY KEY REFERENCES sat_nodes(id), markdown TEXT NOT NULL, state TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS sat_reviews (id TEXT PRIMARY KEY, manifest TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS sat_parses (id TEXT PRIMARY KEY REFERENCES sat_nodes(id), evidence_id TEXT NOT NULL REFERENCES sat_documents(evidence_id), artifact TEXT NOT NULL)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS sat_parse_evidence ON sat_parses(evidence_id)"
            )
            for resource in load_catalog():
                payload = {
                    **resource,
                    "state": "catalogued",
                    "provenance_state": "unverified",
                    "content_ingested": False,
                }
                # El catálogo es editorial y puede actualizarse; no toca CTV/CLV.
                db.execute(
                    "INSERT INTO sat_nodes VALUES (?, 'Resource', ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload WHERE sat_nodes.kind='Resource'",
                    (resource["id"], canonical(payload)),
                )
                for topic in resource["topics"]:
                    self._node(db, f"topic:{topic}", "Topic", {"label": topic})
                    self._edge(
                        db,
                        resource["id"],
                        "about",
                        f"topic:{topic}",
                        {
                            "rule": "official-catalog-v1",
                            "provenance_state": "catalogued",
                        },
                    )

    @contextmanager
    def _transaction(self):
        with closing(sqlite3.connect(self.path, timeout=30)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            with db:
                yield db

    @contextmanager
    def _reader(self):
        # Nodos, aristas y documentos deben proceder del mismo snapshot incluso
        # si otra conexión confirma una revisión entre dos SELECT.
        with closing(sqlite3.connect(self.path, timeout=30)) as db:
            db.execute("BEGIN")
            with db:
                yield db

    @staticmethod
    def _node(db, identity, kind, payload):
        encoded = canonical(payload)
        existing = db.execute(
            "SELECT kind,payload FROM sat_nodes WHERE id=?", (identity,)
        ).fetchone()
        if existing and existing != (kind, encoded):
            raise ValueError(f"Identidad en conflicto: {identity}")
        db.execute(
            "INSERT OR IGNORE INTO sat_nodes VALUES (?,?,?)", (identity, kind, encoded)
        )

    @staticmethod
    def _get(db, identity, kind):
        row = db.execute(
            "SELECT kind,payload FROM sat_nodes WHERE id=?", (identity,)
        ).fetchone()
        if row is None or row[0] != kind:
            raise ValueError(f"Nodo {kind} inexistente: {identity}")
        return json.loads(row[1])

    @staticmethod
    def _edge(db, source, predicate, target, evidence):
        identity = "edge:" + digest(canonical([source, predicate, target, evidence]))
        db.execute(
            "INSERT OR IGNORE INTO sat_edges VALUES (?,?,?,?,?)",
            (identity, source, predicate, target, canonical(evidence)),
        )

    def stage(
        self,
        evidence: SourceEvidence,
        markdown: str,
        docling_document: dict | None = None,
        *,
        documentary_review=None,
    ) -> dict:
        """Publicar evidencia y candidatos atómicamente, sin Work ni vigencia inventada."""
        if (
            digest(markdown) != evidence.markdown_sha256
            or len(markdown.encode("utf-8")) != evidence.markdown_size_bytes
        ):
            raise ValueError("Hash Markdown no coincide con SourceEvidence")
        if (
            evidence.evidence_id != f"pdf-sha256-{evidence.pdf_sha256}"
            or evidence.provenance_state != "unverified"
        ):
            raise ValueError("Identidad/proveniencia de evidencia inválida")
        spans = candidate_spans(markdown)
        # Copia JSON inmutable, independiente del objeto mutable del conversor.
        layout = json.loads(
            json.dumps(docling_document, ensure_ascii=False, allow_nan=False)
        )
        structure = parse_legal_structure(
            markdown, layout, documentary_review=documentary_review
        )
        layout_hash = digest(canonical(layout)) if layout is not None else None
        artifact = {"structure": structure, "docling_document": layout}
        parse_id = "parse:" + digest(canonical([evidence.evidence_id, artifact]))
        with self._transaction() as db:
            self._node(db, evidence.evidence_id, "Source", asdict(evidence))
            existing = db.execute(
                "SELECT markdown,state FROM sat_documents WHERE evidence_id=?",
                (evidence.evidence_id,),
            ).fetchone()
            if existing and existing[0] != markdown:
                raise ValueError("Conversión divergente para el mismo PDF")
            db.execute(
                "INSERT OR IGNORE INTO sat_documents VALUES (?,?,'pending_review')",
                (evidence.evidence_id, markdown),
            )
            for span in spans:
                identity = "candidate:" + digest(
                    canonical([evidence.evidence_id, span["start"], span["end"]])
                )
                self._node(
                    db,
                    identity,
                    "CandidateText",
                    {**span, "provenance_state": "unverified"},
                )
                self._edge(
                    db,
                    identity,
                    "evidenced_by",
                    evidence.evidence_id,
                    {"rule": "article-boundary-v1", "provenance_state": "unverified"},
                )
            self._node(
                db,
                parse_id,
                "CandidateParse",
                {
                    "evidence_id": evidence.evidence_id,
                    "parser_version": structure["parser_version"],
                    "markdown_sha256": evidence.markdown_sha256,
                    "docling_sha256": layout_hash,
                    "artifact_sha256": digest(canonical(artifact)),
                    "component_count": len(structure["nodes"]),
                    "provenance_state": "unverified",
                    "review_required": True,
                },
            )
            db.execute(
                "INSERT OR IGNORE INTO sat_parses VALUES (?,?,?)",
                (parse_id, evidence.evidence_id, canonical(artifact)),
            )
            audit = {
                "rule": structure["parser_version"],
                "provenance_state": "unverified",
            }
            self._edge(db, parse_id, "evidenced_by", evidence.evidence_id, audit)
            identities = {
                n["id"]: "component:" + digest(canonical([parse_id, n["id"]]))
                for n in structure["nodes"]
            }
            for component in structure["nodes"]:
                identity = identities[component["id"]]
                payload = {
                    k: v for k, v in component.items() if k not in {"id", "parent_id"}
                }
                parent = (
                    identities[component["parent_id"]]
                    if component["parent_id"]
                    else parse_id
                )
                self._node(
                    db,
                    identity,
                    "CandidateComponent",
                    {
                        **payload,
                        "local_id": component["id"],
                        "parent_id": parent,
                        "parse_id": parse_id,
                    },
                )
                self._edge(db, parent, "candidate_contains", identity, audit)
                self._edge(db, identity, "evidenced_by", evidence.evidence_id, audit)
            state = existing[1] if existing else "pending_review"
        return {
            "engine": "sat",
            "write_state": "committed",
            "review_state": state,
            "evidence_id": evidence.evidence_id,
            "candidate_count": len(spans),
            "parse_id": parse_id,
            "structural_candidate_count": len(structure["nodes"]),
            "structure_diagnostic_count": len(structure["diagnostics"]),
            "llm_calls": 0,
        }

    def structure(self, evidence_id: str, parse_id: str | None = None) -> dict:
        """Leer evidencia candidata; no seleccionar silenciosamente entre parses."""
        with self._reader() as db:
            self._get(db, evidence_id, "Source")
            rows = db.execute(
                "SELECT id,artifact FROM sat_parses WHERE evidence_id=? ORDER BY id",
                (evidence_id,),
            ).fetchall()
            if parse_id is not None:
                rows = [row for row in rows if row[0] == parse_id]
            if not rows:
                raise ValueError("Estructura candidata inexistente")
            if len(rows) != 1:
                raise ValueError("Múltiples estructuras: especificar parse_id")
            identity, encoded = rows[0]
            source = self._get(db, identity, "CandidateParse")
            if digest(encoded) != source["artifact_sha256"]:
                raise ValueError("Artefacto estructural alterado")
            return {
                "parse_id": identity,
                "evidence_id": evidence_id,
                **json.loads(encoded),
            }

    @staticmethod
    def _span(markdown: str, span: Span) -> str:
        if (
            span.end > len(markdown)
            or digest(markdown[span.start : span.end]) != span.text_sha256
        ):
            raise ValueError("Fragmento fuera de rango o hash de texto incorrecto")
        return markdown[span.start : span.end]

    def review(self, manifest: ReviewManifest) -> dict:
        """Promover solo un manifiesto local explícito; no es un endpoint de upload.

        Cierres, nuevas versiones, relaciones y auditoría se confirman juntos.
        Cualquier contradicción revierte TODO, incluidas terminaciones anteriores.
        """
        payload = manifest.model_dump(mode="json")
        review_id = "review:" + digest(canonical(payload))
        version_ids = [version_id(unit) for unit in manifest.units]
        if len(set(version_ids)) != len(version_ids):
            raise ValueError("Versiones duplicadas en revisión")
        with self._transaction() as db:
            prior = db.execute(
                "SELECT id FROM sat_reviews WHERE id=?", (review_id,)
            ).fetchone()
            if prior:
                return {
                    "review_id": review_id,
                    "version_ids": version_ids,
                    "write_state": "committed",
                }
            source = self._get(db, manifest.evidence_id, "Source")
            if (source["pdf_sha256"], source["markdown_sha256"]) != (
                manifest.pdf_sha256,
                manifest.markdown_sha256,
            ):
                raise ValueError("Manifiesto no corresponde a la evidencia almacenada")
            resource = self._get(db, manifest.source_resource_id, "Resource")
            if resource["kind"] != "norm":
                raise ValueError("Una guía o servicio no puede ser fuente normativa")
            markdown = db.execute(
                "SELECT markdown FROM sat_documents WHERE evidence_id=?",
                (manifest.evidence_id,),
            ).fetchone()[0]
            audit = {
                "review_id": review_id,
                "evidence_id": manifest.evidence_id,
                "source_url": resource["url"],
                "reviewer": manifest.reviewer,
                "reviewed_at": payload["reviewed_at"],
                "rule": "reviewed-manifest-v1",
            }
            # Primero escribir versiones sin resolver solapamientos; la transacción
            # no será visible hasta aplicar cierres y validar el estado completo.
            for unit in manifest.units:
                text = self._span(markdown, unit)
                target_resource = self._get(db, unit.resource_id, "Resource")
                if target_resource["kind"] != "norm":
                    raise ValueError("Work requiere un recurso normativo")
                wid, vid = work_id(unit.resource_id, unit.component), version_id(unit)
                self._node(
                    db,
                    wid,
                    "Work",
                    {
                        "resource_id": unit.resource_id,
                        "component": unit.component,
                        "label": unit.label,
                    },
                )
                span_audit = {
                    **audit,
                    **unit.model_dump(include={"start", "end", "text_sha256"}),
                }
                self._node(
                    db,
                    vid,
                    "CTV",
                    {
                        "work_id": wid,
                        "scope": unit.scope,
                        "valid_from": str(unit.valid_from),
                        "valid_to": str(unit.valid_to) if unit.valid_to else None,
                        "checked_through": str(manifest.checked_through),
                        "provenance_state": "reviewed",
                        **span_audit,
                    },
                )
                tid = "clv:" + digest(canonical([vid, unit.language, unit.text_sha256]))
                self._node(
                    db,
                    tid,
                    "CLV",
                    {"language": unit.language, "text": text, **span_audit},
                )
                self._edge(db, vid, "version_of", wid, span_audit)
                self._edge(db, vid, "has_text", tid, span_audit)
                self._edge(db, tid, "evidenced_by", manifest.evidence_id, span_audit)
                self._edge(db, wid, "instrument", unit.resource_id, span_audit)
                if unit.parent_component:
                    parent_id = work_id(unit.resource_id, unit.parent_component)
                    self._get(db, parent_id, "Work")
                    if parent_id == wid:
                        raise ValueError("Work no puede ser su propio padre")
                    self._edge(db, parent_id, "has_part", wid, span_audit)
            for action in manifest.actions:
                self._apply_action(db, action, markdown, manifest, audit)
            self._validate_intervals(db)
            for membership in manifest.memberships:
                self._membership(db, membership, audit)
            # Un cierre de CTV puede invalidar membresías publicadas antes.
            for parent_id, child_id in db.execute(
                "SELECT source,target FROM sat_edges WHERE predicate='contains_version'"
            ).fetchall():
                self._validate_membership(db, parent_id, child_id)
            self._reject_cycles(db, "has_part")
            self._reject_cycles(db, "contains_version")
            db.execute(
                "INSERT INTO sat_reviews VALUES (?,?)", (review_id, canonical(payload))
            )
            db.execute(
                "UPDATE sat_documents SET state='reviewed' WHERE evidence_id=?",
                (manifest.evidence_id,),
            )
        return {
            "review_id": review_id,
            "version_ids": version_ids,
            "write_state": "committed",
        }

    def _apply_action(self, db, action, markdown, manifest, audit):
        self._span(markdown, action)
        if len(set(action.terminates)) != len(action.terminates) or len(
            set(action.produces)
        ) != len(action.produces):
            raise ValueError("Objetivos de Action duplicados")
        old = [self._get(db, identity, "CTV") for identity in action.terminates]
        new = [self._get(db, identity, "CTV") for identity in action.produces]
        if action.kind == "amend" and (
            not old
            or sorted(v["work_id"] for v in old) != sorted(v["work_id"] for v in new)
        ):
            raise ValueError(
                "Una reforma requiere versiones anterior/nueva de los mismos Work"
            )
        if action.kind == "enact" and (old or not new):
            raise ValueError("Promulgación inválida")
        if action.kind == "repeal" and (new or not old):
            raise ValueError("Derogación inválida")
        when = str(action.effective_on)
        if action.effective_on > manifest.checked_through:
            raise ValueError("Action fuera de cobertura revisada")
        aid = "action:" + digest(
            canonical([manifest.source_resource_id, action.action_key, when])
        )
        action_audit = {
            **audit,
            **action.model_dump(include={"start", "end", "text_sha256"}),
        }
        self._node(
            db, aid, "Action", {**action.model_dump(mode="json"), **action_audit}
        )
        self._edge(db, aid, "source", manifest.source_resource_id, action_audit)
        self._edge(db, aid, "evidenced_by", manifest.evidence_id, action_audit)
        for identity, version in zip(action.terminates, old):
            if version["valid_from"] >= when or version["valid_to"] not in {None, when}:
                raise ValueError("Terminación no coincide con intervalo anterior")
            if db.execute(
                "SELECT 1 FROM sat_edges WHERE predicate='terminates' AND target=?",
                (identity,),
            ).fetchone():
                raise ValueError("Versión ya terminada por otra Action")
            version["valid_to"] = when
            version["closure_review_id"] = audit["review_id"]
            db.execute(
                "UPDATE sat_nodes SET payload=? WHERE id=?",
                (canonical(version), identity),
            )
            self._edge(db, aid, "terminates", identity, action_audit)
        for identity, version in zip(action.produces, new):
            if (
                version["valid_from"] != when
                or version["review_id"] != audit["review_id"]
            ):
                raise ValueError("Producción no coincide con versión nueva revisada")
            self._edge(db, aid, "produces", identity, action_audit)

    @staticmethod
    def _validate_intervals(db):
        groups = {}
        for (payload,) in db.execute("SELECT payload FROM sat_nodes WHERE kind='CTV'"):
            version = json.loads(payload)
            groups.setdefault((version["work_id"], version["scope"]), []).append(
                version
            )
        for versions in groups.values():
            ordered = sorted(versions, key=lambda v: v["valid_from"])
            for left, right in zip(ordered, ordered[1:]):
                if left["valid_to"] is None or left["valid_to"] > right["valid_from"]:
                    raise ValueError("CTV autoritativas solapadas")

    def _membership(self, db, membership, audit):
        self._validate_membership(
            db, membership.parent_version, membership.child_version
        )
        self._edge(
            db,
            membership.parent_version,
            "contains_version",
            membership.child_version,
            audit,
        )

    def _validate_membership(self, db, parent_id, child_id):
        parent = self._get(db, parent_id, "CTV")
        child = self._get(db, child_id, "CTV")
        if not db.execute(
            "SELECT 1 FROM sat_edges WHERE source=? AND predicate='has_part' AND target=?",
            (parent["work_id"], child["work_id"]),
        ).fetchone():
            raise ValueError("Membresía sin estructura Work explícita")
        if child["valid_from"] > parent["valid_from"] or (
            child["valid_to"] is not None
            and (parent["valid_to"] is None or child["valid_to"] < parent["valid_to"])
        ):
            raise ValueError("Versión hija no cubre intervalo del padre")

    @staticmethod
    def _reject_cycles(db, predicate):
        cycle = db.execute(
            """WITH RECURSIVE reach(a,b) AS (
            SELECT source,target FROM sat_edges WHERE predicate=?
            UNION SELECT reach.a,e.target FROM reach JOIN sat_edges e ON reach.b=e.source WHERE e.predicate=?
            ) SELECT 1 FROM reach WHERE a=b LIMIT 1""",
            (predicate, predicate),
        ).fetchone()
        if cycle:
            raise ValueError("Ciclo en estructura SAT")

    def resolve(
        self, resource_id: str, component: str, as_of: str, scope="PE", language="es"
    ) -> dict:
        """Selección exacta, no semántica. Abstenerse fuera de cobertura o idioma."""
        when = date.fromisoformat(as_of).isoformat()
        if when != as_of:
            raise ValueError("Fecha requerida en formato YYYY-MM-DD")
        wid = work_id(resource_id, component)
        with self._reader() as db:
            versions = [
                (identity, json.loads(payload))
                for identity, payload in db.execute(
                    "SELECT id,payload FROM sat_nodes WHERE kind='CTV'"
                )
            ]
            active = [
                (identity, v)
                for identity, v in versions
                if v["work_id"] == wid
                and v["scope"] == scope
                and v["valid_from"] <= when
                and (v["valid_to"] is None or when < v["valid_to"])
            ]
            if len(active) != 1:
                return {
                    "state": "abstain",
                    "reason": "missing_or_ambiguous_version",
                    "work_id": wid,
                }
            identity, version = active[0]
            if when > version["checked_through"]:
                return {
                    "state": "abstain",
                    "reason": "outside_reviewed_coverage",
                    "work_id": wid,
                }
            texts = [
                json.loads(payload)
                for (payload,) in db.execute(
                    "SELECT n.payload FROM sat_edges e JOIN sat_nodes n ON n.id=e.target WHERE e.source=? AND e.predicate='has_text'",
                    (identity,),
                )
            ]
            texts = [text for text in texts if text["language"] == language]
            if len(texts) != 1:
                return {
                    "state": "abstain",
                    "reason": "missing_or_ambiguous_language",
                    "work_id": wid,
                }
            return {
                "state": "resolved",
                "version_id": identity,
                "version": version,
                "text": texts[0],
                "as_of": when,
            }

    def draft(self, evidence_id: str, resource_id: str) -> dict:
        """Fechas/identidades nulas obligan a revisar antes de promover el borrador."""
        with self._reader() as db:
            source = self._get(db, evidence_id, "Source")
            self._get(db, resource_id, "Resource")
            markdown = db.execute(
                "SELECT markdown FROM sat_documents WHERE evidence_id=?", (evidence_id,)
            ).fetchone()[0]
        return {
            "schema_version": 1,
            "evidence_id": evidence_id,
            "source_resource_id": resource_id,
            "pdf_sha256": source["pdf_sha256"],
            "markdown_sha256": source["markdown_sha256"],
            "reviewer": None,
            "reviewed_at": None,
            "checked_through": None,
            "effective_date_basis": None,
            "units": [
                {
                    "resource_id": resource_id,
                    "component": None,
                    "parent_component": None,
                    "language": "es",
                    "scope": "PE",
                    "valid_from": None,
                    "valid_to": None,
                    **span,
                }
                for span in candidate_spans(markdown)
            ],
            "actions": [],
            "memberships": [],
        }

    def export(self) -> dict:
        with self._reader() as db:
            nodes = [
                {"id": identity, "type": kind, **json.loads(payload)}
                for identity, kind, payload in db.execute(
                    "SELECT id,kind,payload FROM sat_nodes ORDER BY id"
                )
            ]
            edges = [
                {
                    "id": identity,
                    "source": source,
                    "type": predicate,
                    "target": target,
                    "evidence": json.loads(payload),
                }
                for identity, source, predicate, target, payload in db.execute(
                    "SELECT * FROM sat_edges ORDER BY id"
                )
            ]
            documents = [
                {"evidence_id": evidence, "state": state}
                for evidence, state in db.execute(
                    "SELECT evidence_id,state FROM sat_documents ORDER BY evidence_id"
                )
            ]
        return {
            "engine": "sat",
            "schema_version": 1,
            "nodes": nodes,
            "edges": edges,
            "documents": documents,
            "resource_count": sum(n["type"] == "Resource" for n in nodes),
            "reviewed_version_count": sum(n["type"] == "CTV" for n in nodes),
        }
