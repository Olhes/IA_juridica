"""Cassettes: graban y reproducen respuestas de proveedores para correr offline.

Modos: ``replay`` (por defecto; una entrada ausente es un error), ``record``
(graba solo si el llamador ya tiene autorización de red/coste) y
``record_missing``. Nunca se graba una cabecera, clave ni credencial: solo la
solicitud canónica (``key_material``) y la respuesta JSON.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

REPLAY, RECORD, RECORD_MISSING = "replay", "record", "record_missing"
MODES = (REPLAY, RECORD, RECORD_MISSING)


class CassetteMiss(KeyError):
    """No hay respuesta grabada para la solicitud y el modo no permite grabar."""


def canonical_key(material: dict) -> str:
    raw = json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class Cassette:
    def __init__(self, path, mode=REPLAY, meta=None):
        if mode not in MODES:
            raise ValueError(f"Modo de cassette desconocido: {mode}")
        self.path, self.mode = Path(path), mode
        self.meta = dict(meta or {})
        self.entries: dict = {}
        self._dirty = False
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.entries = data.get("entries", {})
            self.meta = {**data.get("meta", {}), **self.meta}

    @property
    def can_record(self) -> bool:
        return self.mode in (RECORD, RECORD_MISSING)

    def get(self, material: dict):
        key = canonical_key(material)
        if self.mode == RECORD:
            return None
        entry = self.entries.get(key)
        return None if entry is None else entry["response"]

    def put(self, material: dict, response) -> None:
        if not self.can_record:
            raise PermissionError("El cassette está en modo replay: no puede grabar")
        self.entries[canonical_key(material)] = {
            "request": material,
            "response": response,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        self._dirty = True

    async def call(self, material: dict, producer):
        """Devuelve la respuesta grabada o, si el modo lo permite, la produce y la graba."""
        cached = self.get(material)
        if cached is not None:
            return cached
        if not self.can_record:
            raise CassetteMiss(
                "Sin respuesta grabada para esta solicitud. Grábala con --run-model-evals "
                "(requiere autorización de red/coste)."
            )
        response = await producer()
        self.put(material, response)
        return response

    def save(self) -> None:
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"meta": self.meta, "entries": dict(sorted(self.entries.items()))}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        self._dirty = False
