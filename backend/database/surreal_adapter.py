"""Native async SurrealDB persistence adapter for auth and conversations.

Uses ``AsyncSurreal`` (WebSocket RPC) directly on the running asyncio loop with
loop-affinity rebinding, idempotent index creation, server-side SurrealQL
filtering/aggregation/pagination, and transactional cascade deletion.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from surrealdb import AsyncSurreal, RecordID
from surrealdb.errors import NotFoundError

from config.settings import settings
from database.errors import DatabaseUnavailableError
from database.surreal_connection import surreal_credentials, surreal_url

logger = logging.getLogger("ia_juridica.surreal")


AUTH_DB = "auth_schema"
CONVERSATIONS_DB = "conversations_schema"

_AUTH_SCHEMA_DDL = (
    "DEFINE TABLE IF NOT EXISTS users SCHEMALESS; "
    "DEFINE INDEX IF NOT EXISTS idx_users_email ON users COLUMNS email UNIQUE; "
    "DEFINE TABLE IF NOT EXISTS roles SCHEMALESS; "
    "DEFINE INDEX IF NOT EXISTS idx_roles_name ON roles COLUMNS name UNIQUE; "
    "DEFINE TABLE IF NOT EXISTS user_roles SCHEMALESS; "
    "DEFINE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles COLUMNS user_id; "
    "DEFINE TABLE IF NOT EXISTS role_permissions SCHEMALESS; "
    "DEFINE INDEX IF NOT EXISTS idx_role_permissions_role ON role_permissions COLUMNS role_id; "
    "DEFINE TABLE IF NOT EXISTS permissions SCHEMALESS;"
)

_CONVERSATIONS_SCHEMA_DDL = (
    "DEFINE TABLE IF NOT EXISTS conversations SCHEMALESS; "
    "DEFINE INDEX IF NOT EXISTS idx_conversations_user_updated ON conversations COLUMNS user_id, updated_at; "
    "DEFINE TABLE IF NOT EXISTS messages SCHEMALESS; "
    "DEFINE INDEX IF NOT EXISTS idx_messages_conversation_created ON messages COLUMNS conversation_id, created_at;"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rid(table: str, identity: Any) -> RecordID:
    return RecordID(table, identity)


def _plain_id(value: Any) -> Any:
    return value.id if isinstance(value, RecordID) else value


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _serialize(value: Any) -> Any:
    """Make metadata JSON-safe before handing it to the SurrealDB SDK."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    return value


def _as_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


async def _open_connection(database: str) -> AsyncSurreal:
    """Open, authenticate, and select namespace/database on a fresh AsyncSurreal client."""
    conn = AsyncSurreal(surreal_url())
    await conn.connect()
    try:
        user, password = surreal_credentials()
        await conn.signin({"username": user, "password": password})
        await conn.use(settings.SURREAL_NAMESPACE, database)
    except Exception:
        await _close_connection(conn)
        raise
    return conn


async def _close_connection(conn: Any) -> None:
    if conn is None:
        return
    try:
        await conn.close()
    except Exception:
        pass


class SurrealAdapter:
    """Native async SurrealDB adapter for auth, RBAC, and chat persistence."""

    def __init__(self):
        self.conn: Optional[AsyncSurreal] = None
        self.conv_conn: Optional[AsyncSurreal] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._init_lock: Optional[asyncio.Lock] = None
        self._lock_loop: Optional[asyncio.AbstractEventLoop] = None
        self._indexes_ready = False

    def _get_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._lock_loop is not loop or self._init_lock is None:
            self._init_lock = asyncio.Lock()
            self._lock_loop = loop
        return self._init_lock

    def _connections_valid_for_current_loop(self) -> bool:
        if self.conn is None or self.conv_conn is None:
            return False
        current_loop = asyncio.get_running_loop()
        if self._loop is not None and self._loop is not current_loop:
            return False
        return True

    # -- connection lifecycle ----------------------------------------------
    async def initialize(self):
        """Connect to both application databases; tolerate an unavailable server."""
        async with self._get_lock():
            current_loop = asyncio.get_running_loop()
            if self._connections_valid_for_current_loop():
                return

            if self._loop is not None and self._loop is not current_loop:
                # Rebinding on a new event loop: close old clients so AsyncSurreal
                # tears down sockets and reconnect/ping tasks cleanly.
                old_conn, old_conv = self.conn, self.conv_conn
                self.conn = None
                self.conv_conn = None
                self._loop = None
                await _close_connection(old_conv)
                await _close_connection(old_conn)

            max_retries = 3
            for attempt in range(max_retries):
                auth_conn = None
                conv_conn = None
                try:
                    logger.info(
                        "SurrealDB connection attempt %s/%s", attempt + 1, max_retries
                    )
                    auth_conn = await _open_connection(AUTH_DB)
                    conv_conn = await _open_connection(CONVERSATIONS_DB)
                    self.conn = auth_conn
                    self.conv_conn = conv_conn
                    self._loop = current_loop
                    await self._ensure_indexes()
                    version = await self._server_version()
                    logger.info("SurrealDB connected version=%s", version)
                    return
                except Exception:
                    await _close_connection(conv_conn)
                    await _close_connection(auth_conn)
                    self.conn = None
                    self.conv_conn = None
                    self._loop = None
                    if attempt < max_retries - 1:
                        await asyncio.sleep(3)
                    else:
                        logger.warning(
                            "SurrealDB unavailable; continuing without persistence"
                        )
                        return

    async def _ensure_indexes(self) -> None:
        if self._indexes_ready:
            return
        await asyncio.gather(
            self._run(_AUTH_SCHEMA_DDL, database=AUTH_DB),
            self._run(_CONVERSATIONS_SCHEMA_DDL, database=CONVERSATIONS_DB),
        )
        self._indexes_ready = True

    async def close(self):
        async with self._get_lock():
            connections = (self.conn, self.conv_conn)
            self.conn = None
            self.conv_conn = None
            self._loop = None
        for connection in connections:
            await _close_connection(connection)
        logger.info("SurrealDB connections closed")

    async def health_check(self) -> Dict[str, Any]:
        if not self._connections_valid_for_current_loop():
            return {
                "status": "unhealthy",
                "database": "surrealdb",
                "error": "Connection not initialized",
                "timestamp": _now(),
            }
        try:
            version = await self._server_version(strict=True)
            return {
                "status": "healthy",
                "database": "surrealdb",
                "version": version,
                "timestamp": _now(),
            }
        except Exception:
            return {
                "status": "unhealthy",
                "database": "surrealdb",
                "timestamp": _now(),
            }

    def is_connected(self) -> bool:
        return self.conn is not None and self.conv_conn is not None

    async def _server_version(self, *, strict: bool = False) -> str:
        if not self.conn:
            if strict:
                raise DatabaseUnavailableError("SurrealDB unavailable")
            return "unknown"
        last_error: Optional[Exception] = None
        for name in ("version", "server_version"):
            attr = getattr(self.conn, name, None)
            if attr is None:
                continue
            if callable(attr):
                try:
                    value = attr()
                    if asyncio.iscoroutine(value):
                        value = await value
                except Exception as error:
                    last_error = error
                    continue
            else:
                value = attr
            if value:
                return str(value)
        if strict and last_error is not None:
            raise last_error
        return "unknown"

    async def _ensure(self):
        if not self._connections_valid_for_current_loop():
            await self.initialize()

    def _conn_for(self, database: str):
        return self.conv_conn if database == CONVERSATIONS_DB else self.conn

    async def _run(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
        database: str = AUTH_DB,
    ) -> List[Dict[str, Any]]:
        connection = self._conn_for(database)
        if connection is None:
            raise DatabaseUnavailableError("SurrealDB unavailable")

        try:
            result = await connection.query(sql, params or {})
        except NotFoundError:
            return []
        if not result:
            return []
        first = result[0]
        return first if isinstance(first, list) else []

    async def _create(self, rid: RecordID, fields: Dict[str, Any], database: str):
        params: Dict[str, Any] = {"rid": rid}
        assignments = []
        for index, (key, value) in enumerate(fields.items()):
            name = f"v{index}"
            params[name] = value
            assignments.append(f"{key} = ${name}")
        await self._run(f"CREATE $rid SET {', '.join(assignments)}", params, database)

    # -- row mapping --------------------------------------------------------
    @staticmethod
    def _conversation(
        row: Dict[str, Any], *, nullable_updated: bool = False
    ) -> Dict[str, Any]:
        created = _iso(row.get("created_at"))
        updated = _iso(row.get("updated_at"))
        return {
            "id": _plain_id(row.get("id")),
            "user_id": row.get("user_id"),
            "title": row.get("title"),
            "language": row.get("language"),
            "created_at": created,
            "updated_at": updated if nullable_updated else (updated or created),
            "metadata": _as_dict(row.get("metadata")),
            "is_active": bool(row.get("is_active", True)),
        }

    @staticmethod
    def _message(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": _plain_id(row.get("id")),
            "conversation_id": row.get("conversation_id"),
            "content": row.get("content"),
            "role": row.get("role"),
            "metadata": _as_dict(row.get("metadata")),
            "created_at": _iso(row.get("created_at")),
        }

    @staticmethod
    def _user(row: Dict[str, Any], *, with_password: bool = False) -> Dict[str, Any]:
        result = {
            "id": _plain_id(row.get("id")),
            "email": row.get("email"),
            "username": row.get("username"),
            "full_name": row.get("full_name"),
            "picture": row.get("picture"),
            "role": row.get("role"),
            "is_active": bool(row.get("is_active", True)),
            "last_login": _iso(row.get("last_login")),
            "created_at": _iso(row.get("created_at")),
        }
        if with_password:
            result["password_hash"] = row.get("password_hash")
        return result

    async def _conversation_row(self, conversation_id: str, owner_id: str):
        rows = await self._run(
            "SELECT * FROM conversations WHERE id = $rid AND user_id = $p0 LIMIT 1",
            {"rid": _rid("conversations", conversation_id), "p0": owner_id},
            CONVERSATIONS_DB,
        )
        return rows[0] if rows else None

    async def _message_counts(self, conversation_ids: List[str]) -> Dict[str, int]:
        if not conversation_ids:
            return {}
        rows = await self._run(
            "SELECT conversation_id, count() AS total FROM messages "
            "WHERE conversation_id INSIDE $ids GROUP BY conversation_id",
            {"ids": list(conversation_ids)},
            CONVERSATIONS_DB,
        )
        return {
            row["conversation_id"]: int(row.get("total", 0))
            for row in rows
            if row.get("conversation_id") is not None
        }

    # -- conversations ------------------------------------------------------
    async def create_conversation(
        self, user_id: str, title: str = None, language: str = "spanish"
    ) -> Dict[str, Any]:
        await self._ensure()
        if not self.conv_conn:
            raise DatabaseUnavailableError("SurrealDB unavailable")

        identity = str(uuid.uuid4())
        timestamp = _now()
        resolved_title = title or f"Conversación en {language}"
        fields = {
            "user_id": user_id,
            "title": resolved_title,
            "language": language,
            "created_at": timestamp,
            "updated_at": timestamp,
            "metadata": {},
            "is_active": True,
        }
        await self._create(_rid("conversations", identity), fields, CONVERSATIONS_DB)
        return {"id": identity, **fields}

    async def get_conversation(
        self, conversation_id: str, owner_id: str
    ) -> Optional[Dict[str, Any]]:
        await self._ensure()
        if not self.conv_conn:
            raise DatabaseUnavailableError("SurrealDB unavailable")
        row = await self._conversation_row(conversation_id, owner_id)
        return self._conversation(row) if row else None

    async def create_message(
        self,
        conversation_id: str,
        owner_id: str,
        content: str,
        role: str,
        metadata: Dict[str, Any] = None,
    ) -> Optional[Dict[str, Any]]:
        await self._ensure()
        if not self.conv_conn:
            raise DatabaseUnavailableError("SurrealDB unavailable")
        if not await self._conversation_row(conversation_id, owner_id):
            return None
        identity = str(uuid.uuid4())
        timestamp = _now()
        serialized_metadata = _serialize(metadata or {})
        await self._run(
            "BEGIN TRANSACTION; "
            "CREATE $rid SET conversation_id = $cid, content = $content, "
            "role = $role, metadata = $meta, created_at = $ts; "
            "UPDATE $conv_rid SET updated_at = $ts; "
            "COMMIT TRANSACTION;",
            {
                "rid": _rid("messages", identity),
                "conv_rid": _rid("conversations", conversation_id),
                "cid": conversation_id,
                "content": content,
                "role": role,
                "meta": serialized_metadata,
                "ts": timestamp,
            },
            CONVERSATIONS_DB,
        )
        return {
            "id": identity,
            "conversation_id": conversation_id,
            "content": content,
            "role": role,
            "metadata": _as_dict(metadata or {}),
            "message_type": "text",
            "tokens_used": 0,
            "model_used": None,
            "created_at": timestamp,
        }

    async def get_conversation_messages(
        self, conversation_id: str, owner_id: str
    ) -> List[Dict[str, Any]]:
        await self._ensure()
        if not self.conv_conn:
            return []
        if not await self._conversation_row(conversation_id, owner_id):
            return []
        rows = await self._run(
            "SELECT * FROM messages WHERE conversation_id = $p0 ORDER BY created_at ASC",
            {"p0": conversation_id},
            CONVERSATIONS_DB,
        )
        return [self._message(row) for row in rows]

    async def get_user_conversations(
        self, user_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        await self._ensure()
        if not self.conv_conn:
            raise DatabaseUnavailableError("SurrealDB unavailable")
        rows = await self._run(
            "SELECT * FROM conversations WHERE user_id = $p0 "
            "ORDER BY updated_at DESC LIMIT $limit",
            {"p0": user_id, "limit": max(0, int(limit))},
            CONVERSATIONS_DB,
        )
        counts = await self._message_counts(
            [_plain_id(row.get("id")) for row in rows]
        )
        result = []
        for row in rows:
            item = self._conversation(row, nullable_updated=True)
            item["message_count"] = counts.get(item["id"], 0)
            result.append(item)
        return result

    async def update_conversation(
        self, conversation_id: str, owner_id: str, update_data: Dict[str, Any]
    ) -> bool:
        await self._ensure()
        if not self.conv_conn:
            return False
        raw = (
            update_data.model_dump()
            if hasattr(update_data, "model_dump")
            else dict(update_data)
        )
        fields: Dict[str, Any] = {}
        if raw.get("title") is not None:
            fields["title"] = raw["title"]
        if "metadata" in raw and raw["metadata"] is not None:
            fields["metadata"] = _serialize(raw["metadata"])
        if raw.get("is_active") is not None:
            fields["is_active"] = raw["is_active"]
        if not fields:
            return False
        fields["updated_at"] = _now()

        params: Dict[str, Any] = {
            "rid": _rid("conversations", conversation_id),
            "owner": owner_id,
        }
        assignments = []
        for index, (key, value) in enumerate(fields.items()):
            name = f"v{index}"
            params[name] = value
            assignments.append(f"{key} = ${name}")
        updated = await self._run(
            f"UPDATE $rid SET {', '.join(assignments)} WHERE user_id = $owner RETURN AFTER",
            params,
            CONVERSATIONS_DB,
        )
        return bool(updated)

    async def delete_conversation(self, conversation_id: str, owner_id: str) -> bool:
        await self._ensure()
        if not self.conv_conn:
            return False
        if not await self._conversation_row(conversation_id, owner_id):
            return False
        await self._run(
            "BEGIN TRANSACTION; "
            "DELETE messages WHERE conversation_id = $cid; "
            "DELETE $rid; "
            "COMMIT TRANSACTION;",
            {"rid": _rid("conversations", conversation_id), "cid": conversation_id},
            CONVERSATIONS_DB,
        )
        return True

    async def search_conversations(
        self, user_id: str, query: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        await self._ensure()
        if not self.conv_conn:
            return []
        cap = max(0, int(limit))
        if cap == 0:
            return []
        needle = (query or "").strip().lower()
        if not needle:
            rows = await self._run(
                "SELECT * FROM conversations WHERE user_id = $p0 "
                "ORDER BY updated_at DESC LIMIT $limit",
                {"p0": user_id, "limit": cap},
                CONVERSATIONS_DB,
            )
            return [self._conversation(row, nullable_updated=True) for row in rows]

        rows = await self._run(
            "SELECT * FROM conversations WHERE user_id = $p0 ORDER BY updated_at DESC",
            {"p0": user_id},
            CONVERSATIONS_DB,
        )
        if not rows:
            return []

        title_matches = set()
        candidate_ids: List[str] = []
        title_count = 0
        for row in rows:
            cid = _plain_id(row.get("id"))
            if needle in (row.get("title") or "").lower():
                title_matches.add(cid)
                title_count += 1
                if title_count >= cap:
                    break
            else:
                candidate_ids.append(cid)

        message_matches = set()
        if candidate_ids:
            matched_rows = await self._run(
                "SELECT conversation_id FROM messages "
                "WHERE conversation_id INSIDE $ids "
                "AND string::lowercase(content) CONTAINS $needle "
                "GROUP BY conversation_id",
                {"ids": candidate_ids, "needle": needle},
                CONVERSATIONS_DB,
            )
            message_matches = {
                row["conversation_id"]
                for row in matched_rows
                if row.get("conversation_id") is not None
            }

        result = []
        for row in rows:
            cid = _plain_id(row.get("id"))
            if cid not in title_matches and cid not in message_matches:
                continue
            result.append(self._conversation(row, nullable_updated=True))
            if len(result) >= cap:
                break
        return result

    # -- users and authorization -------------------------------------------
    async def create_user(
        self,
        email: str,
        username: str,
        password_hash: str,
        full_name: str = None,
        picture: str = None,
        role: str = "user",
    ) -> Optional[Dict[str, Any]]:
        await self._ensure()
        if not self.conn:
            raise DatabaseUnavailableError("SurrealDB unavailable")
        identity = str(uuid.uuid4())
        fields = {
            "email": email,
            "username": username,
            "password_hash": password_hash,
            "full_name": full_name,
            "picture": picture,
            "role": role,
            "is_active": True,
            "created_at": _now(),
        }
        await self._create(_rid("users", identity), fields, AUTH_DB)
        result = self._user({"id": _rid("users", identity), **fields})
        result.pop("last_login", None)
        return result

    async def update_user(
        self, user_id: str, updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        await self._ensure()
        if not self.conn:
            raise DatabaseUnavailableError("SurrealDB unavailable")
        fields = {
            key: value
            for key, value in (updates or {}).items()
            if key in ("full_name", "picture", "username") and value is not None
        }
        if not fields:
            return None
        rid = _rid("users", user_id)
        params: Dict[str, Any] = {"rid": rid}
        assignments = []
        for index, (key, value) in enumerate(fields.items()):
            name = f"v{index}"
            params[name] = value
            assignments.append(f"{key} = ${name}")
        rows = await self._run(
            f"UPDATE $rid SET {', '.join(assignments)} RETURN AFTER",
            params,
            AUTH_DB,
        )
        if not rows:
            return None
        result = self._user(rows[0])
        result.pop("last_login", None)
        return result

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        await self._ensure()
        if not self.conn:
            return None
        rows = await self._run(
            "SELECT * FROM users WHERE email = $p0 AND is_active = true LIMIT 1",
            {"p0": email},
        )
        return self._user(rows[0], with_password=True) if rows else None

    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        if not user_id:
            return None
        await self._ensure()
        if not self.conn:
            return None
        rows = await self._run(
            "SELECT * FROM $rid LIMIT 1", {"rid": _rid("users", user_id)}
        )
        return self._user(rows[0]) if rows else None

    async def update_last_login(self, user_id: str) -> bool:
        await self._ensure()
        if not self.conn:
            return False
        await self._run(
            "UPDATE $rid SET last_login = $p0",
            {"rid": _rid("users", user_id), "p0": _now()},
        )
        return True

    async def get_user_roles(self, user_id: str) -> List[Dict[str, Any]]:
        await self._ensure()
        if not self.conn:
            return []
        assignments = await self._run(
            "SELECT * FROM user_roles WHERE user_id = $p0", {"p0": user_id}
        )
        roles: List[Dict[str, Any]] = []
        if assignments:
            role_rids = [
                _rid("roles", assignment["role_id"])
                for assignment in assignments
                if assignment.get("role_id") is not None
            ]
            fetched = (
                await self._run(
                    "SELECT * FROM roles WHERE id INSIDE $rids", {"rids": role_rids}
                )
                if role_rids
                else []
            )
            by_id = {_plain_id(row.get("id")): row for row in fetched}
            for assignment in assignments:
                role = by_id.get(assignment.get("role_id"))
                if not role:
                    continue
                roles.append(
                    {
                        "id": _plain_id(role.get("id")),
                        "name": role.get("name"),
                        "description": role.get("description")
                        or f"Role: {role.get('name')}",
                        "assigned_at": _iso(assignment.get("assigned_at"))
                        or _iso(assignment.get("created_at")),
                    }
                )
        if roles:
            return roles
        rows = await self._run(
            "SELECT role FROM $rid LIMIT 1", {"rid": _rid("users", user_id)}
        )
        name = rows[0].get("role") if rows else None
        if not name:
            return []
        return [
            {
                "id": name,
                "name": name,
                "description": f"Role: {name}",
                "assigned_at": None,
            }
        ]

    async def get_user_permissions(self, user_id: str) -> List[str]:
        await self._ensure()
        if not self.conn:
            return []
        assignments = await self._run(
            "SELECT role_id FROM user_roles WHERE user_id = $p0", {"p0": user_id}
        )
        role_ids = [
            assignment["role_id"]
            for assignment in assignments
            if assignment.get("role_id") is not None
        ]
        if not role_ids:
            return []
        grants = await self._run(
            "SELECT permission_id FROM role_permissions WHERE role_id INSIDE $rids",
            {"rids": role_ids},
        )
        perm_rids = [
            _rid("permissions", grant["permission_id"])
            for grant in grants
            if grant.get("permission_id") is not None
        ]
        if not perm_rids:
            return []
        permissions = await self._run(
            "SELECT name FROM permissions WHERE id INSIDE $pids", {"pids": perm_rids}
        )
        return [row["name"] for row in permissions if row.get("name")]

    async def assign_role_to_user(
        self, user_id: str, role_name: str, assigned_by: str = None
    ) -> bool:
        await self._ensure()
        if not self.conn:
            return False
        rows = await self._run(
            "SELECT id FROM roles WHERE name = $p0 LIMIT 1", {"p0": role_name}
        )
        if not rows:
            return False
        role_id = _plain_id(rows[0].get("id"))
        rid = _rid("user_roles", [user_id, role_id])
        existing = await self._run("SELECT id FROM $rid LIMIT 1", {"rid": rid})
        if existing:
            return True
        await self._create(
            rid,
            {
                "user_id": user_id,
                "role_id": role_id,
                "assigned_by": assigned_by,
                "assigned_at": _now(),
            },
            AUTH_DB,
        )
        return True

    async def has_permission(self, user_id: str, permission_name: str) -> bool:
        return permission_name in await self.get_user_permissions(user_id)


database_adapter = SurrealAdapter()
