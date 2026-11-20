"""SurrealDB implementation of the application's database adapter contract.

The public async surface mirrors :class:`PostgreSQLAdapter` so auth, chat and
quality-access can run unchanged against SurrealDB while PostgreSQL stays in
place as the rollback backend. Every query is parameterized; dynamic column
names are whitelisted rather than taken from user input.
"""

import asyncio
from datetime import datetime, timezone
import json
import uuid
from typing import Any, Dict, List, Optional

from surrealdb import RecordID
from surrealdb.errors import NotFoundError

from database.postgres_adapter_final import DatabaseUnavailableError
from database.surreal_connection import close_surreal, connect_surreal


AUTH_DB = "auth_schema"
CONVERSATIONS_DB = "conversations_schema"

_DEFINED_TABLES: set[str] = set()


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


class SurrealAdapter:
    """SurrealDB-backed replacement for PostgreSQLAdapter."""

    def __init__(self):
        self.conn = None
        self.conv_conn = None
        # Serializa la inicialización: sin esto, dos requests concurrentes ven
        # `conn is None` a la vez, abren su propio par de websockets y el que
        # pierde queda huérfano sin cerrarse (fuga de sockets).
        self._init_lock = asyncio.Lock()

    # -- connection lifecycle ----------------------------------------------
    async def initialize(self):
        """Connect to both application databases; tolerate an unavailable server."""
        async with self._init_lock:
            if self.conn is not None and self.conv_conn is not None:
                return

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    print(f"SurrealDB connection attempt {attempt + 1}/{max_retries}...")

                    def connect_sync():
                        auth = connect_surreal(AUTH_DB)
                        try:
                            conversations = connect_surreal(CONVERSATIONS_DB)
                        except Exception:
                            close_surreal(auth)
                            raise
                        return auth, conversations

                    conn, conv_conn = await asyncio.get_event_loop().run_in_executor(
                        None, connect_sync
                    )
                    self.conn, self.conv_conn = conn, conv_conn
                    version = await self._server_version()
                    print(f"SurrealDB connected: {version}")
                    print("SurrealDB connection initialized")
                    return
                except Exception:
                    self.conn = None
                    self.conv_conn = None
                    if attempt < max_retries - 1:
                        await asyncio.sleep(3)
                    else:
                        print("SurrealDB unavailable; continuing without persistence")
                        return

    async def close(self):
        async with self._init_lock:
            connections, self.conn, self.conv_conn = (self.conn, self.conv_conn), None, None
        for connection in connections:
            if connection is not None:
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda conn=connection: close_surreal(conn)
                )
        print("SurrealDB connections closed")

    async def health_check(self) -> Dict[str, Any]:
        if not self.conn:
            return {
                "status": "unhealthy",
                "database": "surrealdb",
                "error": "Connection not initialized",
                "timestamp": _now(),
            }
        try:
            version = await self._server_version()
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
        return self.conn is not None

    async def _server_version(self) -> str:
        if not self.conn:
            return "unknown"

        def read():
            for name in ("server_version", "version"):
                value = getattr(self.conn, name, None)
                if callable(value):
                    try:
                        value = value()
                    except Exception:
                        continue
                if value:
                    return str(value)
            return "unknown"

        return await asyncio.get_event_loop().run_in_executor(None, read)

    async def _ensure(self):
        if self.conn is None or self.conv_conn is None:
            await self.initialize()

    def _conn_for(self, database: str):
        return self.conv_conn if database == CONVERSATIONS_DB else self.conn

    async def _run(self, sql: str, params: Optional[Dict[str, Any]] = None,
                   database: str = AUTH_DB) -> List[Dict[str, Any]]:
        connection = self._conn_for(database)
        if connection is None:
            raise DatabaseUnavailableError("SurrealDB unavailable")

        def execute_sync():
            return connection.query(sql, params or {}).execute()

        try:
            result = await asyncio.get_event_loop().run_in_executor(None, execute_sync)
        except NotFoundError:
            # A table with no migrated rows is simply empty.
            return []
        return result[0] if result else []

    async def _create(self, rid: RecordID, fields: Dict[str, Any], database: str):
        params: Dict[str, Any] = {"rid": rid}
        assignments = []
        for index, (key, value) in enumerate(fields.items()):
            name = f"v{index}"
            params[name] = value
            assignments.append(f"{key} = ${name}")
        await self._run(f"CREATE $rid SET {', '.join(assignments)}", params, database)

    async def _update_record(self, rid: RecordID, fields: Dict[str, Any], database: str):
        params: Dict[str, Any] = {"rid": rid}
        assignments = []
        for index, (key, value) in enumerate(fields.items()):
            name = f"v{index}"
            params[name] = value
            assignments.append(f"{key} = ${name}")
        await self._run(f"UPDATE $rid SET {', '.join(assignments)}", params, database)

    async def _ensure_table(self, name: str):
        if name in _DEFINED_TABLES:
            return
        await self._run(f"DEFINE TABLE IF NOT EXISTS {name} SCHEMALESS")
        _DEFINED_TABLES.add(name)

    # -- row mapping --------------------------------------------------------
    @staticmethod
    def _conversation(row: Dict[str, Any], *, nullable_updated: bool = False) -> Dict[str, Any]:
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
    def _message(row: Dict[str, Any], *, with_defaults: bool = False) -> Dict[str, Any]:
        result = {
            "id": _plain_id(row.get("id")),
            "conversation_id": row.get("conversation_id"),
            "content": row.get("content"),
            "role": row.get("role"),
            "metadata": _as_dict(row.get("metadata")),
            "created_at": _iso(row.get("created_at")),
        }
        if with_defaults:
            result.update({"message_type": "text", "tokens_used": 0, "model_used": None})
        return result

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
        rows = await self._run("SELECT conversation_id FROM messages", database=CONVERSATIONS_DB)
        wanted = set(conversation_ids)
        counts: Dict[str, int] = {}
        for row in rows:
            key = row.get("conversation_id")
            if key in wanted:
                counts[key] = counts.get(key, 0) + 1
        return counts

    # -- conversations ------------------------------------------------------
    async def create_conversation(self, user_id: str, title: str = None,
                                  language: str = "spanish") -> Dict[str, Any]:
        await self._ensure()
        if not self.conv_conn:
            raise DatabaseUnavailableError("SurrealDB unavailable")

        owner = "00000000-0000-0000-0000-000000000001" if user_id == "debug-user" else user_id
        identity = str(uuid.uuid4())
        timestamp = _now()
        resolved_title = title or f"Conversación en {language}"
        fields = {
            "user_id": owner,
            "title": resolved_title,
            "language": language,
            "created_at": timestamp,
            "updated_at": timestamp,
            "metadata": {},
            "is_active": True,
        }
        await self._create(_rid("conversations", identity), fields, CONVERSATIONS_DB)
        return {
            "id": identity,
            "user_id": owner,
            "title": resolved_title,
            "language": language,
            "created_at": timestamp,
            "updated_at": timestamp,
            "metadata": {},
            "is_active": True,
        }

    async def get_conversation(self, conversation_id: str,
                               owner_id: str) -> Optional[Dict[str, Any]]:
        await self._ensure()
        if not self.conv_conn:
            raise DatabaseUnavailableError("SurrealDB unavailable")
        row = await self._conversation_row(conversation_id, owner_id)
        return self._conversation(row) if row else None

    async def create_message(self, conversation_id: str, owner_id: str, content: str,
                             role: str, metadata: Dict[str, Any] = None
                             ) -> Optional[Dict[str, Any]]:
        await self._ensure()
        if not self.conv_conn:
            raise DatabaseUnavailableError("SurrealDB unavailable")
        if not await self._conversation_row(conversation_id, owner_id):
            return None
        identity = str(uuid.uuid4())
        timestamp = _now()
        fields = {
            "conversation_id": conversation_id,
            "content": content,
            "role": role,
            "metadata": _serialize(metadata or {}),
            "created_at": timestamp,
        }
        await self._create(_rid("messages", identity), fields, CONVERSATIONS_DB)
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

    async def get_conversation_messages(self, conversation_id: str,
                                        owner_id: str) -> List[Dict[str, Any]]:
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

    async def update_cultural_context(self, conversation_id: str, owner_id: str,
                                      cultural_context: str, legal_domain: str = None,
                                      user_preferences: Dict[str, Any] = None
                                      ) -> Optional[Dict[str, Any]]:
        await self._ensure()
        if not self.conv_conn:
            raise DatabaseUnavailableError("SurrealDB unavailable")
        if not await self._conversation_row(conversation_id, owner_id):
            return None
        await self._ensure_table("cultural_contexts")
        rid = _rid("cultural_contexts", conversation_id)
        existing = await self._run("SELECT * FROM $rid LIMIT 1", {"rid": rid}, CONVERSATIONS_DB)
        timestamp = _now()
        fields = {
            "conversation_id": conversation_id,
            "cultural_context": cultural_context,
            "legal_domain": legal_domain,
            "user_preferences": _serialize(user_preferences or {}),
            "updated_at": timestamp,
        }
        if existing:
            await self._update_record(rid, fields, CONVERSATIONS_DB)
            created = _iso(existing[0].get("created_at")) or timestamp
        else:
            fields["created_at"] = timestamp
            await self._create(rid, fields, CONVERSATIONS_DB)
            created = timestamp
        return {
            "id": conversation_id,
            "conversation_id": conversation_id,
            "cultural_context": cultural_context,
            "legal_domain": legal_domain,
            "user_preferences": _as_dict(user_preferences or {}),
            "updated_at": timestamp,
            "created_at": created,
        }

    async def list_conversations(self, owner_id: str, limit: int = 50,
                                 offset: int = 0) -> List[Dict[str, Any]]:
        await self._ensure()
        if not self.conv_conn:
            return []
        rows = await self._run(
            "SELECT * FROM conversations WHERE user_id = $p0 ORDER BY updated_at DESC",
            {"p0": owner_id},
            CONVERSATIONS_DB,
        )
        page = rows[offset:offset + limit]
        counts = await self._message_counts([_plain_id(row.get("id")) for row in page])
        return [
            {
                "id": _plain_id(row.get("id")),
                "title": row.get("title"),
                "language": row.get("language"),
                "created_at": _iso(row.get("created_at")),
                "updated_at": _iso(row.get("updated_at")),
                "message_count": counts.get(_plain_id(row.get("id")), 0),
            }
            for row in page
        ]

    async def get_user_conversations(self, user_id: str,
                                     limit: int = 50) -> List[Dict[str, Any]]:
        await self._ensure()
        if not self.conv_conn:
            raise DatabaseUnavailableError("SurrealDB unavailable")
        rows = await self._run(
            "SELECT * FROM conversations WHERE user_id = $p0 ORDER BY updated_at DESC",
            {"p0": user_id},
            CONVERSATIONS_DB,
        )
        page = rows[:limit]
        counts = await self._message_counts([_plain_id(row.get("id")) for row in page])
        result = []
        for row in page:
            item = self._conversation(row, nullable_updated=True)
            item["message_count"] = counts.get(item["id"], 0)
            result.append(item)
        return result

    async def update_conversation(self, conversation_id: str, owner_id: str,
                                  update_data: Dict[str, Any]) -> bool:
        await self._ensure()
        if not self.conv_conn:
            return False
        raw = update_data.model_dump() if hasattr(update_data, "model_dump") else dict(update_data)
        fields: Dict[str, Any] = {}
        if raw.get("title") is not None:
            fields["title"] = raw["title"]
        if "metadata" in raw and raw["metadata"] is not None:
            fields["metadata"] = _serialize(raw["metadata"])
        if raw.get("is_active") is not None:
            fields["is_active"] = raw["is_active"]
        if not fields:
            return False
        if not await self._conversation_row(conversation_id, owner_id):
            return False
        fields["updated_at"] = _now()
        await self._update_record(_rid("conversations", conversation_id), fields,
                                  CONVERSATIONS_DB)
        return True

    async def delete_conversation(self, conversation_id: str, owner_id: str) -> bool:
        await self._ensure()
        if not self.conv_conn:
            return False
        if not await self._conversation_row(conversation_id, owner_id):
            return False
        await self._run("DELETE $rid", {"rid": _rid("conversations", conversation_id)},
                        CONVERSATIONS_DB)
        return True

    async def search_conversations(self, user_id: str, query: str,
                                   limit: int = 20) -> List[Dict[str, Any]]:
        await self._ensure()
        if not self.conv_conn:
            return []
        rows = await self._run(
            "SELECT * FROM conversations WHERE user_id = $p0 ORDER BY updated_at DESC",
            {"p0": user_id},
            CONVERSATIONS_DB,
        )
        messages = await self._run("SELECT conversation_id, content FROM messages",
                                   database=CONVERSATIONS_DB)
        content_by_conversation: Dict[str, List[str]] = {}
        for message in messages:
            content_by_conversation.setdefault(message.get("conversation_id"), []).append(
                message.get("content") or ""
            )
        needle = (query or "").lower()
        result = []
        for row in rows:
            identity = _plain_id(row.get("id"))
            title = row.get("title") or ""
            contents = content_by_conversation.get(identity, [])
            if needle not in title.lower() and not any(
                needle in content.lower() for content in contents
            ):
                continue
            result.append(self._conversation(row, nullable_updated=True))
            if len(result) >= limit:
                break
        return result

    # -- users and authorization -------------------------------------------
    async def create_user(self, email: str, username: str, password_hash: str,
                          full_name: str = None, picture: str = None,
                          role: str = 'user') -> Optional[Dict[str, Any]]:
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

    async def update_user(self, user_id: str,
                          updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        await self._ensure()
        if not self.conn:
            raise DatabaseUnavailableError("SurrealDB unavailable")
        fields = {
            key: value for key, value in (updates or {}).items()
            if key in ("full_name", "picture", "username") and value is not None
        }
        if not fields:
            return None
        rid = _rid("users", user_id)
        rows = await self._run("SELECT * FROM $rid LIMIT 1", {"rid": rid})
        if not rows:
            return None
        await self._update_record(rid, fields, AUTH_DB)
        result = self._user({**rows[0], **fields})
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
            all_roles = await self._run("SELECT * FROM roles")
            by_id = {_plain_id(row.get("id")): row for row in all_roles}
            for assignment in assignments:
                role = by_id.get(assignment.get("role_id"))
                if not role:
                    continue
                roles.append({
                    "id": _plain_id(role.get("id")),
                    "name": role.get("name"),
                    "description": role.get("description") or f"Role: {role.get('name')}",
                    "assigned_at": _iso(assignment.get("assigned_at"))
                    or _iso(assignment.get("created_at")),
                })
        if roles:
            return roles
        # Legacy compatibility: the role lives on the users row as well.
        rows = await self._run(
            "SELECT role FROM $rid LIMIT 1", {"rid": _rid("users", user_id)}
        )
        name = rows[0].get("role") if rows else None
        if not name:
            return []
        return [{
            "id": name,
            "name": name,
            "description": f"Role: {name}",
            "assigned_at": None,
        }]

    async def get_user_permissions(self, user_id: str) -> List[str]:
        await self._ensure()
        if not self.conn:
            return []
        assignments = await self._run(
            "SELECT * FROM user_roles WHERE user_id = $p0", {"p0": user_id}
        )
        if not assignments:
            return []
        role_ids = {assignment.get("role_id") for assignment in assignments}
        grants = await self._run("SELECT * FROM role_permissions")
        permission_ids = {
            grant.get("permission_id") for grant in grants
            if grant.get("role_id") in role_ids
        }
        if not permission_ids:
            return []
        permissions = await self._run("SELECT * FROM permissions")
        return [
            row.get("name") for row in permissions
            if _plain_id(row.get("id")) in permission_ids and row.get("name")
        ]

    async def assign_role_to_user(self, user_id: str, role_name: str,
                                  assigned_by: str = None) -> bool:
        await self._ensure()
        if not self.conn:
            return False
        rows = await self._run(
            "SELECT * FROM roles WHERE name = $p0 LIMIT 1", {"p0": role_name}
        )
        if not rows:
            return False
        role_id = _plain_id(rows[0].get("id"))
        await self._ensure_table("user_roles")
        rid = _rid("user_roles", [user_id, role_id])
        existing = await self._run("SELECT * FROM $rid LIMIT 1", {"rid": rid})
        if existing:
            return True
        await self._create(rid, {
            "user_id": user_id,
            "role_id": role_id,
            "assigned_by": assigned_by,
            "assigned_at": _now(),
        }, AUTH_DB)
        return True

    async def has_permission(self, user_id: str, permission_name: str) -> bool:
        return permission_name in await self.get_user_permissions(user_id)


database_adapter = SurrealAdapter()
