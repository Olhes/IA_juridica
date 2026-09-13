# Security Model

## Anonymous Identity

The backend issues a versioned, expiring HMAC-SHA256 session in the
`ia_juridica_session` cookie. The cookie is `HttpOnly`, uses `SameSite=Lax` by
default, and is always `Secure` in production. Clients bootstrap it with
`POST /session/bootstrap`; request bodies and query parameters never select an
owner.

The browser may keep non-sensitive UX preferences such as language, alias, or
installation hints in local storage. Local storage is not authentication and
must not contain bearer tokens, session tokens, prompts, responses, or chat
ownership identifiers.

Chats remain in PostgreSQL and Redis. Every conversation cache key and every
read/write SQL operation includes the cookie-derived principal. Foreign and
unknown conversation IDs both return the same 404 response.

## Required Production Configuration

- Set `ENVIRONMENT=production`.
- Set `ANONYMOUS_SESSION_SECRET` to at least 32 random bytes. Do not reuse
  `SECRET_KEY` or `ADMIN_API_KEY`.
- Set `RATE_LIMIT_STORAGE_URI` to shared storage, normally Redis, when running
  multiple workers.
- Enumerate exact `CORS_ORIGINS`; wildcard origins, methods, and headers are
  rejected by startup validation.
- Leave `ADMIN_ENDPOINTS_ENABLED=false` unless administration is needed. If it
  is enabled, set a separate `ADMIN_API_KEY` and send it in `X-API-Key`.
- API docs and OpenAPI are disabled by default in production. Enable them only
  deliberately with `API_DOCS_ENABLED=true`.

For local development, `http://localhost:3000` and `http://localhost:8000` are
cross-origin but same-site, so `SameSite=Lax` plus `credentials: include` works.
For production frontends and APIs on different registrable domains,
`SameSite=None; Secure` is required and introduces CSRF exposure. Prefer a
same-site API subdomain or reverse proxy. If cross-site deployment is
unavoidable, add explicit CSRF protection before changing the cookie setting.

## Existing Demo Conversations

Existing rows owned by the historical demo UUID are intentionally inaccessible
to new anonymous visitors. They are never claimed automatically. An operator
may preview and then explicitly reassign one known owner to one chosen
principal:

```powershell
uv run python backend/scripts/reassign_conversation_owner.py `
  --source-owner <historical-owner-uuid> `
  --new-owner <principal-id-from-bootstrap>

uv run python backend/scripts/reassign_conversation_owner.py `
  --source-owner <historical-owner-uuid> `
  --new-owner <principal-id-from-bootstrap> `
  --apply --confirm REASSIGN-CONVERSATIONS
```

Run the dry mode first and back up PostgreSQL. The utility updates only rows
whose current owner exactly matches `--source-owner`; messages follow through
their conversation foreign key. Clear only the affected owner's conversation
cache keys after an applied migration.

## Uploads

Admin PDF uploads require an enabled admin API and valid key. The backend
generates the stored basename, streams to disk with `MAX_FILE_SIZE`, checks the
`.pdf` extension, `application/pdf` media type, and `%PDF-` signature, uses
exclusive file creation, and removes partial raw/processed files on failure.
The sanitized original basename is metadata only.
