"""Feedback 👍/👎 de las respuestas y cola de candidatos al gold.

* Todo feedback guarda solo etiquetas y números (calificación, motivo, idioma, estado de evidencia,
  calidad del quechua) y un hash del propietario para no duplicar votos.
* El texto de la consulta y de la respuesta se guarda **únicamente** si la persona lo autoriza
  (``share_text``) y califica con 👎: entra a la cola de candidatos, pendiente de revisión humana.
* Un candidato aceptado NO se agrega al gold: se exporta como esqueleto para que abogados escriban los
  hechos y citas; el gold sigue siendo revisado a ciegas por dos personas.

Persistencia en un archivo JSON local (``FEEDBACK_DIR``), reescrito de forma atómica. En un despliegue con
disco efímero se pierde al reiniciar: para producción conviene moverlo a PostgreSQL.
"""

import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

Reason = Literal["incorrecta", "incompleta", "sin_fuentes", "mala_traduccion", "confusa", "otro"]
Decision = Literal["accept", "reject"]
MAX_TEXT = 4000


class FeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    rating: Literal["up", "down"]
    reason: Optional[Reason] = None
    comment: Optional[str] = Field(default=None, max_length=500)
    conversation_id: Optional[str] = Field(default=None, max_length=64)
    language: Literal["spanish", "quechua"] = "spanish"
    evidence_status: Optional[Literal["retrieved", "insufficient_evidence"]] = None
    translation_quality: Optional[Literal["alta", "media", "baja"]] = None
    share_text: bool = False

    @model_validator(mode="after")
    def _down_needs_a_reason(self):
        if self.rating == "down" and self.reason is None:
            raise ValueError("un 👎 necesita un motivo")
        if self.rating == "up" and self.reason is not None:
            raise ValueError("un 👍 no lleva motivo")
        return self


def _owner_hash(owner_id: str) -> str:
    return hashlib.sha256(f"feedback:{owner_id}".encode()).hexdigest()[:16]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FeedbackStore:
    def __init__(self, directory):
        self.path = Path(directory) / "feedback.json"
        self._lock = threading.Lock()
        self._items: list = []
        if self.path.exists():
            try:
                self._items = json.loads(self.path.read_text(encoding="utf-8")).get("items", [])
            except (OSError, ValueError):
                self._items = []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"schema": 1, "items": self._items}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        os.replace(temporary, self.path)

    def add(self, owner_id: str, item: FeedbackIn, *, query: Optional[str] = None, answer: Optional[str] = None) -> dict:
        owner = _owner_hash(owner_id)
        candidate = item.share_text and item.rating == "down" and bool(query)
        record = {
            "id": uuid.uuid4().hex,
            "created_at": _now(),
            "owner": owner,
            "request_id": item.request_id,
            "rating": item.rating,
            "reason": item.reason,
            "comment": (item.comment or "").strip() or None,
            "language": item.language,
            "evidence_status": item.evidence_status,
            "translation_quality": item.translation_quality,
            "queue_status": "pending" if candidate else None,
            "text_unavailable": bool(item.share_text and item.rating == "down" and not query),
        }
        if candidate:
            record["query"] = query[:MAX_TEXT]
            record["answer"] = (answer or "")[:MAX_TEXT]
        with self._lock:
            self._items = [i for i in self._items if not (i["owner"] == owner and i["request_id"] == item.request_id)]
            self._items.append(record)
            self._save()
        return record

    def queue(self, status: str = "pending") -> list:
        with self._lock:
            return [dict(i) for i in self._items if i.get("queue_status") == status]

    def decide(self, item_id: str, decision: Decision) -> Optional[dict]:
        with self._lock:
            for item in self._items:
                if item["id"] == item_id and item.get("queue_status") == "pending":
                    item["queue_status"] = "accepted" if decision == "accept" else "rejected"
                    item["decided_at"] = _now()
                    self._save()
                    return dict(item)
        return None

    def summary(self) -> dict:
        with self._lock:
            items = list(self._items)
        reasons: dict = {}
        for item in items:
            if item["rating"] == "down":
                reasons[item["reason"]] = reasons.get(item["reason"], 0) + 1
        return {
            "total": len(items),
            "up": sum(i["rating"] == "up" for i in items),
            "down": sum(i["rating"] == "down" for i in items),
            "reasons": reasons,
            "queue": {s: sum(i.get("queue_status") == s for i in items) for s in ("pending", "accepted", "rejected")},
        }

    def export_candidates(self) -> list:
        """Esqueletos para que abogados redacten el caso; no son gold ni traen hechos."""
        with self._lock:
            accepted = [i for i in self._items if i.get("queue_status") == "accepted"]
        return [
            {"source": "feedback", "status": "candidate", "reviewers": [], "query": i["query"], "language": i["language"],
             "reason": i["reason"], "note": "Redactar hechos exigidos con cita de segmento; el gold lo revisan dos abogados a ciegas."}
            for i in accepted
        ]
