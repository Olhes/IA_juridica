"""Voyage REST con cache contextual, cuota local persistente y errores sin secretos.

Solo reintenta 429 explícitos, nunca timeouts ambiguos. La reserva se conserva
ante error. Los procesos de la aplicación comparten caché y cuota en la base de datos.
"""

from contextlib import closing, contextmanager
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sqlite3
import time
from email.utils import parsedate_to_datetime

import httpx
from surrealdb import RecordID
from surrealdb.errors import NotFoundError, SurrealError

from database.surreal_connection import close_surreal, connect_surreal

from .sat import fingerprint


class _VoyagePostgres:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, args=()):
        if sql == "BEGIN IMMEDIATE":
            # A transaction and its advisory lock are already active.
            return None
        sql = sql.replace("?", "%s").replace("max(until,excluded.until)", "greatest(voyage_cooldown.until,excluded.until)")
        if sql.startswith("INSERT OR IGNORE INTO voyage_usage"):
            sql = sql.replace("INSERT OR IGNORE", "INSERT") + " ON CONFLICT(day) DO NOTHING"
        if sql.startswith("INSERT OR REPLACE INTO voyage_cache"):
            sql = sql.replace("INSERT OR REPLACE", "INSERT") + " ON CONFLICT(key) DO UPDATE SET result=excluded.result,tokens=excluded.tokens"
        return self.connection.execute(sql, args)

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()


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
        cache_path: Path | None = None,
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
        connect=None,
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
        if (cache_path is None) == (connect is None):
            raise ValueError("Configura un solo almacenamiento de caché Voyage")
        self.connect = connect
        self.path = Path(cache_path) if cache_path is not None else None
        self.cache_only = cache_only
        if not cache_only and self.path is not None:
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
            except (sqlite3.Error, SurrealError):
                raise VoyageError("Caché Voyage ausente o incompatible") from None
            return
        with self._db() as db:
            if self.connect:
                db.execute("BEGIN IMMEDIATE")
            db.execute(
                "CREATE TABLE IF NOT EXISTS voyage_cache (key TEXT PRIMARY KEY, result TEXT NOT NULL, tokens INTEGER NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS voyage_usage (day TEXT PRIMARY KEY, requests INTEGER NOT NULL, reserved INTEGER NOT NULL, actual INTEGER NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS voyage_rate (scope TEXT, model TEXT, started DOUBLE PRECISION, reserved INTEGER)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS voyage_cooldown (scope TEXT, model TEXT, until DOUBLE PRECISION, PRIMARY KEY(scope,model))"
            )

    def _db(self):
        if self.connect:
            return self._postgres_db()
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

    @contextmanager
    def _postgres_db(self):
        with self.connect() as connection:
            if self.cache_only:
                connection.execute("SET TRANSACTION READ ONLY")
            else:
                connection.execute("SELECT pg_advisory_xact_lock(6591427708186)")
                connection.execute("CREATE SCHEMA IF NOT EXISTS sat_voyage")
            connection.execute("SET LOCAL search_path TO sat_voyage, pg_catalog")
            yield _VoyagePostgres(connection)

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


# ── SurrealDB voyage storage ──────────────────────────────────────────────────
# VoyageProvider emits a small, fixed SQL dialect. _VoyagePostgres rewrites it
# into PostgreSQL syntax before it reaches the connection, so the shim below
# only needs to translate that rewritten subset into SurrealQL.

_VOYAGE_COLUMNS = {
    "voyage_cache": ("key", "result", "tokens"),
    "voyage_usage": ("day", "requests", "reserved", "actual"),
    "voyage_rate": ("scope", "model", "started", "reserved"),
    "voyage_cooldown": ("scope", "model", "until"),
}
_VOYAGE_TABLES = tuple(_VOYAGE_COLUMNS)


def _plain_id(value):
    return value.id if isinstance(value, RecordID) else value


class _SurrealVoyageCursor:
    """Minimal DB-API cursor returned by the shim's execute()."""

    def __init__(self, rows=()):
        self._rows = [tuple(row) for row in rows]
        self.rowcount = len(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def __iter__(self):
        return iter(self._rows)


class _SurrealVoyageConnection:
    """Use an interactive transaction for each Voyage storage operation."""

    def __init__(self):
        self.connection = connect_surreal("sat_voyage")
        try:
            with self.connection.begin_transaction() as transaction:
                for table in _VOYAGE_TABLES:
                    transaction.query(f"DEFINE TABLE IF NOT EXISTS {table} SCHEMALESS").execute()
            self.transaction = self.connection.begin_transaction()
        except Exception:
            close_surreal(self.connection)
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close()
        return False

    def close(self):
        close_surreal(self.connection)
        self.connection = None

    def commit(self):
        if self.transaction is not None:
            self.transaction.commit()
            self.transaction = None

    def rollback(self):
        if self.transaction is not None:
            self.transaction.cancel()
            self.transaction = None

    def _run(self, sql, params=None):
        try:
            result = self.transaction.query(sql, params or {}).execute()
        except NotFoundError:
            return []
        return result[0] if result else []

    @staticmethod
    def _bind(sql, args):
        names = []

        def replace(_match):
            names.append(f"p{len(names)}")
            return "$" + names[-1]

        sql = re.sub(r"%s|\?", replace, sql)
        return sql, {name: args[index] for index, name in enumerate(names)}

    @staticmethod
    def _resolve(token, bound, sql):
        if re.fullmatch(r"\$p\d+", token):
            return bound[token[1:]]
        if re.fullmatch(r"-?\d+(?:\.\d+)?", token):
            return float(token) if "." in token else int(token)
        if token.upper() == "NULL":
            return None
        if len(token) >= 2 and token[0] == "'" and token[-1] == "'":
            return token[1:-1]
        raise NotImplementedError(f"Unsupported voyage SQL value {token!r} in: {sql}")

    @staticmethod
    def _where(fragment, sql):
        conditions = []
        for part in re.split(r"\s+AND\s+", fragment.strip(), flags=re.I):
            match = re.fullmatch(r"\s*(\w+)\s*(=|<=|>=|<|>)\s*(\S+)\s*", part)
            if not match:
                raise NotImplementedError(f"Unsupported voyage WHERE clause in: {sql}")
            column, operator, token = match.groups()
            if not any(column in columns for columns in _VOYAGE_COLUMNS.values()):
                raise NotImplementedError(f"Unsupported voyage column {column!r} in: {sql}")
            conditions.append(f"{column} {operator} {token}")
        return " AND ".join(conditions)

    @staticmethod
    def _project(rows, columns):
        output = []
        for record in rows:
            output.append(tuple(
                _plain_id(record.get(column)) if column == "id" else record.get(column)
                for column in columns
            ))
        return output

    @staticmethod
    def _rid(table, values):
        if table == "voyage_cooldown":
            return RecordID(table, [values[0], values[1]])
        if table in ("voyage_cache", "voyage_usage"):
            return RecordID(table, values[0])
        return None

    def execute(self, sql, args=()):
        original = sql
        stripped = sql.strip()
        upper = stripped.upper()

        if upper.startswith(("SET ", "BEGIN", "SELECT PG_ADVISORY", "CREATE SCHEMA",
                             "CREATE TABLE")):
            return _SurrealVoyageCursor()

        sql, bound = self._bind(sql, tuple(args))

        if upper.startswith("SELECT "):
            return self._select(sql, bound, original)
        if upper.startswith("INSERT "):
            return self._insert(sql, bound, original)
        if upper.startswith("UPDATE "):
            return self._update(sql, bound, original)
        if upper.startswith("DELETE "):
            return self._delete(sql, bound, original)
        raise NotImplementedError(f"Unsupported voyage SQL: {original}")

    def _select(self, sql, bound, original):
        match = re.match(
            r"^\s*SELECT\s+(.+?)\s+FROM\s+(\w+)\b(.*)$", sql, re.I | re.S
        )
        if not match:
            raise NotImplementedError(f"Unsupported voyage SELECT: {original}")
        columns_raw, table, tail = match.groups()
        if table not in _VOYAGE_COLUMNS:
            raise NotImplementedError(f"Unsupported voyage table {table!r}: {original}")
        columns = [column.strip() for column in columns_raw.split(",")]
        tail = tail.strip()
        where = order = limit = ""
        where_match = re.search(r"\bWHERE\s+(.+?)(?=\bORDER\s+BY\b|\bLIMIT\b|$)", tail, re.I | re.S)
        if where_match:
            where = self._where(where_match.group(1), original)
        order_match = re.search(r"\bORDER\s+BY\s+(\w+)", tail, re.I)
        if order_match:
            order = f" ORDER BY {order_match.group(1)}"
        limit_match = re.search(r"\bLIMIT\s+(\d+)", tail, re.I)
        if limit_match:
            limit = f" LIMIT {limit_match.group(1)}"
        query = f"SELECT * FROM {table}"
        if where:
            query += f" WHERE {where}"
        query += order + limit
        rows = self._run(query, bound)
        return _SurrealVoyageCursor(self._project(rows, columns))

    def _insert(self, sql, bound, original):
        match = re.match(
            r"^\s*INSERT\s+INTO\s+(\w+)\s+VALUES\s*\((.*?)\)\s*(.*)$", sql, re.I | re.S
        )
        if not match:
            raise NotImplementedError(f"Unsupported voyage INSERT: {original}")
        table, values_raw, tail = match.groups()
        columns = _VOYAGE_COLUMNS.get(table)
        if columns is None:
            raise NotImplementedError(f"Unsupported voyage table {table!r}: {original}")
        tokens = [token.strip() for token in values_raw.split(",")]
        if len(tokens) != len(columns):
            raise NotImplementedError(f"Unsupported voyage INSERT arity: {original}")
        values = [self._resolve(token, bound, original) for token in tokens]
        record = dict(zip(columns, values))
        rid = self._rid(table, values)

        existing = []
        if rid is not None:
            existing = self._run("SELECT * FROM $rid LIMIT 1", {"rid": rid})

        do_update = "DO UPDATE" in tail.upper()
        if existing and not do_update:
            return _SurrealVoyageCursor()  # ON CONFLICT DO NOTHING

        if existing and do_update:
            target = f"UPDATE $rid SET "
            updates = {}
            if table == "voyage_cache":
                updates = {"result": values[1], "tokens": values[2]}
            elif table == "voyage_usage":
                updates = {
                    "requests": values[1], "reserved": values[2], "actual": values[3]
                }
            elif table == "voyage_cooldown":
                current = existing[0].get("until")
                updates = {"until": max(float(current or 0), float(values[2]))}
            else:
                raise NotImplementedError(f"Unsupported voyage upsert: {original}")
            params = {"rid": rid}
            assignments = []
            for index, (key, value) in enumerate(updates.items()):
                name = f"v{index}"
                params[name] = value
                assignments.append(f"{key} = ${name}")
            self._run(target + ", ".join(assignments), params)
            return _SurrealVoyageCursor()

        fields = dict(record)
        params = {"rid": rid} if rid is not None else {}
        assignments = []
        for index, (key, value) in enumerate(fields.items()):
            name = f"v{index}"
            params[name] = value
            assignments.append(f"{key} = ${name}")
        query = f"CREATE $rid SET " if rid is not None else f"CREATE {table} SET "
        self._run(query + ", ".join(assignments), params)
        return _SurrealVoyageCursor()

    def _update(self, sql, bound, original):
        match = re.match(
            r"^\s*UPDATE\s+(\w+)\s+SET\s+(.*?)\s+WHERE\s+(.+)$", sql, re.I | re.S
        )
        if not match:
            raise NotImplementedError(f"Unsupported voyage UPDATE: {original}")
        table, assignments_raw, where = match.groups()
        if table not in _VOYAGE_COLUMNS:
            raise NotImplementedError(f"Unsupported voyage table {table!r}: {original}")
        rows = self._run(
            f"SELECT * FROM {table} WHERE {self._where(where, original)}", bound
        )
        assignments = {}
        for part in assignments_raw.split(","):
            item = re.fullmatch(r"\s*(\w+)\s*=\s*(.+?)\s*", part, re.S)
            if not item:
                raise NotImplementedError(f"Unsupported voyage UPDATE: {original}")
            column, expression = item.groups()
            if column not in _VOYAGE_COLUMNS[table]:
                raise NotImplementedError(f"Unsupported voyage column {column!r}: {original}")
            arithmetic = re.fullmatch(r"(\w+)\s*\+\s*(\S+)", expression)
            if arithmetic and arithmetic.group(1) == column:
                token = arithmetic.group(2)
                delta = self._resolve(token, bound, original)
                assignments[column] = ("increment", delta)
            else:
                assignments[column] = ("set", self._resolve(expression, bound, original))
        for row in rows:
            rid = row.get("id")
            fields = {}
            for column, (kind, value) in assignments.items():
                fields[column] = (
                    (row.get(column) or 0) + value if kind == "increment" else value
                )
            params = {"rid": rid}
            updates = []
            for index, (column, value) in enumerate(fields.items()):
                name = f"v{index}"
                params[name] = value
                updates.append(f"{column} = ${name}")
            self._run(f"UPDATE $rid SET {', '.join(updates)}", params)
        return _SurrealVoyageCursor()

    def _delete(self, sql, bound, original):
        match = re.match(
            r"^\s*DELETE\s+(?:FROM\s+)?(\w+)\s+WHERE\s+(.+)$", sql, re.I | re.S
        )
        if not match:
            raise NotImplementedError(f"Unsupported voyage DELETE: {original}")
        table, where = match.groups()
        if table not in _VOYAGE_COLUMNS:
            raise NotImplementedError(f"Unsupported voyage table {table!r}: {original}")
        self._run(
            f"DELETE FROM {table} WHERE {self._where(where, original)}", bound
        )
        return _SurrealVoyageCursor()


def connect_surreal_voyage():
    """Zero-arg factory returning a psycopg-like shim over sat_voyage."""
    return _SurrealVoyageConnection()
