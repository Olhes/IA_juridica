"""Voyage REST con cache contextual, cuota local persistente y errores sin secretos.

Solo reintenta 429 explícitos, nunca timeouts ambiguos. La reserva se conserva
ante error. Todos los procesos deben compartir este archivo para compartir cuota.
"""

from contextlib import closing
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
import time
from email.utils import parsedate_to_datetime

import httpx

from .sat import fingerprint


class VoyageError(RuntimeError):
    pass


class VoyageCacheMiss(VoyageError):
    """Resultado no calculado: no es abstención ni habilita una llamada API."""


class VoyageRateLimit(VoyageError):
    """Sin cuerpo remoto ni credenciales; Retry-After se acota por el caller."""

    def __init__(self, retry_after=61, *, sent=False):
        super().__init__("Voyage respondió HTTP 429; límite de velocidad")
        self.retry_after = retry_after
        self.sent = sent


class VoyageProvider:
    EMBED_MODEL = "voyage-context-4"
    RERANK_MODEL = "rerank-3-lite"

    def __init__(
        self,
        api_key: str,
        cache_path: Path,
        *,
        dimension=1024,
        daily_requests=100,
        daily_token_reservation=100_000,
        requests_per_minute=3,
        token_bound_per_minute=9000,
        max_429_retries=1,
        max_wait_seconds=125,
        clock=time.time,
        sleep=time.sleep,
        transport=None,
        cache_only=False,
    ):
        if type(cache_only) is not bool:
            raise ValueError("cache_only requiere booleano")
        if not cache_only and (not api_key or not api_key.strip()):
            raise VoyageError("VOYAGE_API_KEY no configurada")
        if dimension not in {256, 512, 1024, 2048}:
            raise ValueError("Dimensión Voyage no válida")
        if daily_requests < 1 or daily_token_reservation < 1:
            raise ValueError("Cuotas deben ser positivas")
        if requests_per_minute < 1 or token_bound_per_minute < 1:
            raise ValueError("Límites por minuto deben ser positivos")
        if not 0 <= max_429_retries <= 3 or not 0 <= max_wait_seconds <= 300:
            raise ValueError("Espera/reintentos fuera de rango")
        self._key = api_key
        self.path = Path(cache_path)
        self.cache_only = cache_only
        if not cache_only:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.dimension = dimension
        self.daily_requests = daily_requests
        self.daily_tokens = daily_token_reservation
        self.transport = transport
        self.rpm = requests_per_minute
        self.tpm = token_bound_per_minute
        self.retries = max_429_retries
        self.max_wait = max_wait_seconds
        self.clock, self.sleep = clock, sleep
        self.account_scope = fingerprint(["voyage-account", api_key])
        if cache_only:
            try:
                with self._db() as db:
                    db.execute("SELECT key,result,tokens FROM voyage_cache LIMIT 0")
                    db.execute(
                        "SELECT day,requests,reserved,actual FROM voyage_usage LIMIT 0"
                    )
            except sqlite3.Error:
                raise VoyageError("Caché Voyage ausente o incompatible") from None
            return
        with self._db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS voyage_cache (key TEXT PRIMARY KEY, result TEXT NOT NULL, tokens INTEGER NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS voyage_usage (day TEXT PRIMARY KEY, requests INTEGER NOT NULL, reserved INTEGER NOT NULL, actual INTEGER NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS voyage_rate (scope TEXT, model TEXT, started REAL, reserved INTEGER)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS voyage_cooldown (scope TEXT, model TEXT, until REAL, PRIMARY KEY(scope,model))"
            )

    def _db(self):
        if self.cache_only:
            return closing(
                sqlite3.connect(
                    self.path.resolve().as_uri() + "?mode=ro",
                    uri=True,
                    timeout=60,
                    isolation_level=None,
                )
            )
        return closing(sqlite3.connect(self.path, timeout=60, isolation_level=None))

    def usage(self):
        day = datetime.fromtimestamp(self.clock(), timezone.utc).date().isoformat()
        with self._db() as db:
            row = db.execute(
                "SELECT requests,reserved,actual FROM voyage_usage WHERE day=?", (day,)
            ).fetchone()
        return dict(
            zip(
                ("requests", "reserved_token_bound", "reported_tokens"),
                row or (0, 0, 0),
            )
        )

    def _reserve(self, key, model, reservation):
        if reservation > self.tpm:
            raise VoyageError(
                "Solicitud supera cota local TPM; reducir lote/candidatos"
            )
        waited = 0.0
        while True:
            with self._db() as db:
                db.execute("BEGIN IMMEDIATE")
                cached = db.execute(
                    "SELECT result FROM voyage_cache WHERE key=?", (key,)
                ).fetchone()
                if cached:
                    db.commit()
                    return json.loads(cached[0]), None
                now = self.clock()
                day = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
                db.execute(
                    "INSERT OR IGNORE INTO voyage_usage VALUES (?,0,0,0)", (day,)
                )
                requests, reserved = db.execute(
                    "SELECT requests,reserved FROM voyage_usage WHERE day=?", (day,)
                ).fetchone()
                if (
                    requests >= self.daily_requests
                    or reserved + reservation > self.daily_tokens
                ):
                    db.rollback()
                    raise VoyageError(
                        "Cuota local Voyage agotada; revisar dashboard y presupuesto"
                    )
                db.execute("DELETE FROM voyage_rate WHERE started<=?", (now - 61,))
                rows = db.execute(
                    "SELECT started,reserved FROM voyage_rate WHERE scope=? AND model=? ORDER BY started",
                    (self.account_scope, model),
                ).fetchall()
                cooldown = db.execute(
                    "SELECT until FROM voyage_cooldown WHERE scope=? AND model=?",
                    (self.account_scope, model),
                ).fetchone()
                wait = max(0, cooldown[0] - now) if cooldown else 0
                if len(rows) >= self.rpm:
                    wait = max(wait, rows[-self.rpm][0] + 61 - now)
                remaining = sum(row[1] for row in rows) + reservation
                for started, bound in rows:
                    if remaining <= self.tpm:
                        break
                    wait = max(wait, started + 61 - now)
                    remaining -= bound
                if wait > 0:
                    db.rollback()
                else:
                    db.execute(
                        "UPDATE voyage_usage SET requests=requests+1,reserved=reserved+? WHERE day=?",
                        (reservation, day),
                    )
                    db.execute(
                        "INSERT INTO voyage_rate VALUES (?,?,?,?)",
                        (self.account_scope, model, now, reservation),
                    )
                    # Confirmar ANTES de red: un crash/timeout no libera presupuesto.
                    db.commit()
                    return None, day
            if waited + wait > self.max_wait:
                raise VoyageRateLimit(wait)
            self.sleep(wait)
            waited += wait

    def _retry_after(self, response):
        value = response.headers.get("Retry-After", "61")
        try:
            seconds = float(value)
        except ValueError:
            try:
                seconds = parsedate_to_datetime(value).timestamp() - self.clock()
            except (ValueError, TypeError, OverflowError):
                seconds = 61
        return max(1, seconds) if math.isfinite(seconds) else 61

    def _call(self, endpoint, payload, reservation, parse):
        key = fingerprint(["voyage-rest-v1", endpoint, payload])
        if self.cache_only:
            with self._db() as db:
                row = db.execute(
                    "SELECT result FROM voyage_cache WHERE key=?", (key,)
                ).fetchone()
            if row is None:
                raise VoyageCacheMiss(
                    "Resultado Voyage no disponible en caché de solo lectura"
                )
            return json.loads(row[0]), {"requests": 0, "tokens": 0, "cache_hits": 1}
        failed_requests = 0
        for attempt in range(self.retries + 1):
            try:
                result, usage = self._attempt(
                    endpoint, payload, reservation, parse, key
                )
                usage["requests"] += failed_requests
                return result, usage
            except VoyageRateLimit as error:
                failed_requests += int(error.sent)
                if (
                    not error.sent
                    or attempt == self.retries
                    or error.retry_after > self.max_wait
                ):
                    raise
                # El cooldown persistido se respeta en _reserve, incluso tras reinicio.
        raise AssertionError("unreachable")

    def _attempt(self, endpoint, payload, reservation, parse, key):
        cached, day = self._reserve(key, payload["model"], reservation)
        if cached is not None:
            return cached, {"requests": 0, "tokens": 0, "cache_hits": 1}
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT result FROM voyage_cache WHERE key=?", (key,)
            ).fetchone()
            if row:
                db.commit()
                return json.loads(row[0]), {"requests": 0, "tokens": 0, "cache_hits": 1}
            try:
                with httpx.Client(
                    timeout=45, transport=self.transport, follow_redirects=False
                ) as client:
                    response = client.post(
                        "https://api.voyageai.com/v1/" + endpoint,
                        headers={"Authorization": "Bearer " + self._key},
                        json=payload,
                    )
                if response.status_code == 429:
                    delay = self._retry_after(response)
                    db.execute(
                        "INSERT INTO voyage_cooldown VALUES (?,?,?) ON CONFLICT(scope,model) DO UPDATE SET until=max(until,excluded.until)",
                        (self.account_scope, payload["model"], self.clock() + delay),
                    )
                    db.commit()
                    raise VoyageRateLimit(delay, sent=True)
                if response.status_code != 200:
                    raise VoyageError(f"Voyage respondió HTTP {response.status_code}")
                data = response.json()
                tokens = data["usage"]["total_tokens"]
                if type(tokens) is not int or tokens < 0:
                    raise ValueError("usage inválido")
                result = parse(data)
            except VoyageError:
                db.rollback()
                raise
            except Exception:
                db.rollback()
                raise VoyageError(
                    "Fallo de transporte o contrato Voyage; no se reintentó"
                ) from None
            # No guardar textos de usuario ni documentos devueltos por la API.
            db.execute(
                "INSERT OR REPLACE INTO voyage_cache VALUES (?,?,?)",
                (key, json.dumps(result, allow_nan=False), tokens),
            )
            db.execute(
                "UPDATE voyage_usage SET actual=actual+?,reserved=reserved+? WHERE day=?",
                (tokens, max(0, tokens - reservation), day),
            )
            db.commit()
            return result, {"requests": 1, "tokens": tokens, "cache_hits": 0}

    def embed(self, groups: list[list[str]], *, input_type="document"):
        """Cache por documento contextual completo; otros grupos no lo invalidan."""
        if input_type not in {"document", "query"} or not groups or len(groups) > 1000:
            raise ValueError("Entradas contextualizadas inválidas")
        if any(
            not group or (input_type == "query" and len(group) != 1) for group in groups
        ):
            raise ValueError("Grupo contextual inválido")
        if sum(map(len, groups)) > 16000 or any(
            not isinstance(text, str) or not text.strip()
            for group in groups
            for text in group
        ):
            raise ValueError("Chunks inválidos")
        bounds = [sum(len(t.encode()) + 64 for t in group) for group in groups]
        # El pacing de red no aplica a un resultado ya calculado en modo ro.
        limit = 30000 if self.cache_only else min(30000, self.tpm)
        if any(bound > limit for bound in bounds):
            raise ValueError(
                "Documento contextual supera cota; no se divide ni trunca silenciosamente"
            )
        keys = [
            fingerprint(
                [
                    "voyage-context-group-v1",
                    self.EMBED_MODEL,
                    self.dimension,
                    input_type,
                    group,
                ]
            )
            for group in groups
        ]
        output = [None] * len(groups)
        usage = {"requests": 0, "tokens": 0, "cache_hits": 0}
        missing = []
        with self._db() as db:
            for i, key in enumerate(keys):
                row = db.execute(
                    "SELECT result FROM voyage_cache WHERE key=?", (key,)
                ).fetchone()
                if row:
                    output[i] = json.loads(row[0])
                    usage["cache_hits"] += 1
                else:
                    missing.append(i)
        if missing and self.cache_only:
            raise VoyageCacheMiss(
                "Grupos Voyage no disponibles en caché de solo lectura"
            )
        while missing:
            batch, size = [], 0
            while missing and size + bounds[missing[0]] <= limit:
                index = missing.pop(0)
                batch.append(index)
                size += bounds[index]
            vectors, consumed = self._embed_batch(
                [groups[i] for i in batch], input_type=input_type
            )
            for key in usage:
                usage[key] += consumed[key]
            with self._db() as db:
                db.execute("BEGIN IMMEDIATE")
                for index, vector in zip(batch, vectors, strict=True):
                    output[index] = vector
                    db.execute(
                        "INSERT OR REPLACE INTO voyage_cache VALUES (?,?,0)",
                        (keys[index], json.dumps(vector, allow_nan=False)),
                    )
                db.commit()
        return output, usage

    def _embed_batch(self, groups: list[list[str]], *, input_type="document"):
        if input_type not in {"document", "query"} or not groups or len(groups) > 1000:
            raise ValueError("Entradas contextualizadas inválidas")
        if any(
            not group or (input_type == "query" and len(group) != 1) for group in groups
        ):
            raise ValueError("Cada grupo requiere chunks; query requiere un solo texto")
        texts = [text for group in groups for text in group]
        if (
            any(not isinstance(text, str) or not text.strip() for text in texts)
            or len(texts) > 16000
        ):
            raise ValueError("Chunks inválidos")
        # Cota conservadora UTF-8 + margen, no tokenizer Voyage ni tokens facturados.
        reservation = sum(len(text.encode("utf-8")) + 64 for text in texts)
        if reservation > 30000:
            raise ValueError(
                "Lote contextual supera cota local; dividir por grupos/versiones"
            )
        payload = {
            "model": self.EMBED_MODEL,
            "inputs": groups,
            "input_type": input_type,
            "output_dimension": self.dimension,
            "output_dtype": "float",
            "enable_auto_chunking": False,
        }

        def parse(data):
            if data.get("model", self.EMBED_MODEL) != self.EMBED_MODEL:
                raise ValueError("Modelo inesperado")
            rows = data["data"]
            if (
                any(type(r["index"]) is not int for r in rows)
                or len(rows) != len(groups)
                or {r["index"] for r in rows} != set(range(len(groups)))
            ):
                raise ValueError("Grupos incompletos")
            output = []
            for row in sorted(rows, key=lambda r: r["index"]):
                expected = len(groups[row["index"]])
                chunks = row["data"]
                if (
                    any(type(r["index"]) is not int for r in chunks)
                    or len(chunks) != expected
                    or {r["index"] for r in chunks} != set(range(expected))
                ):
                    raise ValueError("Chunks incompletos")
                vectors = [
                    c["embedding"] for c in sorted(chunks, key=lambda r: r["index"])
                ]
                if any(
                    len(v) != self.dimension
                    or not all(type(x) in {int, float} and math.isfinite(x) for x in v)
                    or not any(v)
                    for v in vectors
                ):
                    raise ValueError("Vector inválido")
                output.append(vectors)
            return output

        return self._call("contextualizedembeddings", payload, reservation, parse)

    def rerank(self, query: str, documents: list[str], *, top_k=5):
        if (
            not query.strip()
            or not documents
            or not 1 <= top_k <= len(documents) <= 100
        ):
            raise ValueError("Rerank inválido")
        if len(query.encode()) > 7500 or any(
            not doc.strip() or len((query + doc).encode()) > 30000 for doc in documents
        ):
            raise ValueError("Rerank supera cota de contexto local")
        reservation = len(documents) * (len(query.encode()) + 64) + sum(
            len(d.encode()) for d in documents
        )
        if reservation > 550000:
            raise ValueError("Rerank supera cota total local")
        payload = {
            "model": self.RERANK_MODEL,
            "query": query,
            "documents": documents,
            "top_k": top_k,
            "truncation": False,
            "return_documents": False,
        }

        def parse(data):
            rows = data["data"]
            indices = [r["index"] for r in rows]
            if (
                len(rows) != top_k
                or len(set(indices)) != len(indices)
                or any(
                    type(i) is not int or not 0 <= i < len(documents) for i in indices
                )
            ):
                raise ValueError("Índices rerank inválidos")
            pairs = [(r["index"], r["relevance_score"]) for r in rows]
            if any(
                type(score) not in {int, float} or not math.isfinite(score)
                for _, score in pairs
            ):
                raise ValueError("Score rerank inválido")
            return sorted(pairs, key=lambda pair: (-pair[1], pair[0]))

        return self._call("rerank", payload, reservation, parse)
