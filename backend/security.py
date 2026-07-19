import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request, Response, Security
from fastapi.security import APIKeyHeader
from slowapi import Limiter

from config.settings import settings


logger = logging.getLogger("ia_juridica.security")
SESSION_VERSION = 1
admin_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass(frozen=True)
class Principal:
    id: str
    expires_at: int


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_session(principal_id: Optional[str] = None, now: Optional[int] = None) -> tuple[str, Principal]:
    issued_at = int(time.time() if now is None else now)
    principal_id = principal_id or str(uuid.uuid4())
    expires_at = issued_at + settings.ANONYMOUS_SESSION_TTL_DAYS * 86400
    payload = {
        "exp": expires_at,
        "iat": issued_at,
        "sub": str(uuid.UUID(principal_id)),
        "v": SESSION_VERSION,
    }
    encoded = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = hmac.new(
        settings.ANONYMOUS_SESSION_SECRET.encode("utf-8"),
        encoded.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{encoded}.{_b64encode(signature)}", Principal(payload["sub"], expires_at)


def verify_session(token: str, now: Optional[int] = None) -> Optional[Principal]:
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected_signature = hmac.new(
            settings.ANONYMOUS_SESSION_SECRET.encode("utf-8"),
            encoded.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(expected_signature, _b64decode(supplied_signature)):
            return None
        payload = json.loads(_b64decode(encoded))
        current_time = int(time.time() if now is None else now)
        if payload.get("v") != SESSION_VERSION or int(payload["exp"]) <= current_time:
            return None
        principal_id = str(uuid.UUID(payload["sub"]))
        return Principal(principal_id, int(payload["exp"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def principal_from_request(request: Request) -> Optional[Principal]:
    token = request.cookies.get(settings.ANONYMOUS_SESSION_COOKIE_NAME)
    return verify_session(token) if token else None


async def require_principal(request: Request) -> Principal:
    principal = principal_from_request(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="Anonymous session required")
    return principal


def set_session_cookie(response: Response, token: str, principal: Principal) -> None:
    response.set_cookie(
        key=settings.ANONYMOUS_SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.ANONYMOUS_SESSION_TTL_DAYS * 86400,
        expires=datetime.fromtimestamp(principal.expires_at, timezone.utc),
        path="/",
        domain=settings.ANONYMOUS_SESSION_COOKIE_DOMAIN,
        secure=settings.session_cookie_secure(),
        httponly=True,
        samesite=settings.ANONYMOUS_SESSION_COOKIE_SAMESITE,
    )


async def verify_admin_api_key(
    api_key: Optional[str] = Security(admin_api_key_header),
) -> bool:
    if not settings.ADMIN_ENDPOINTS_ENABLED or not settings.ADMIN_API_KEY:
        raise HTTPException(status_code=404, detail="Not found")
    if not api_key or not secrets.compare_digest(api_key, settings.ADMIN_API_KEY):
        raise HTTPException(status_code=403, detail="Invalid admin credentials")
    return True


def client_ip_key(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    try:
        address = ipaddress.ip_address(host)
        host = str(getattr(address, "ipv4_mapped", None) or address)
    except ValueError:
        host = host.lower()
    return f"ip:{host}"


def rate_limit_key(request: Request) -> str:
    return client_ip_key(request)


limiter = Limiter(
    key_func=rate_limit_key,
    storage_uri=settings.RATE_LIMIT_STORAGE_URI,
    enabled=settings.RATE_LIMIT_ENABLED,
)
