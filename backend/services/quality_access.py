"""Acceso a las vistas de calidad: clave de administración o una persona con rol ``admin``.

La clave de administración (``X-API-Key``) sirve para scripts y CI y **nunca** viaja al navegador. Las personas
inician sesión y se les comprueba el rol ``admin`` en la base de datos, igual que ``GET /auth/me``.
"""

import logging
import secrets
from typing import Optional

import jwt
from fastapi import HTTPException, Request, Security

from config.settings import settings
from security import admin_api_key_header

ADMIN_ROLE = "admin"
logger = logging.getLogger("ia_juridica.quality_access")


async def roles_from_session(request: Request) -> Optional[list]:
    """Roles del usuario de la cookie ``access_token`` o ``None`` si no hay sesión válida."""
    token = request.cookies.get("access_token")
    if not token:
        return None
    from database.postgres_adapter_final import PostgreSQLAdapter
    from modules.auth.services.security import AuthService as SecurityService  # mismo alias que auth_routes

    try:
        payload = SecurityService().decode_token(token, is_refresh=False)
    except (jwt.InvalidTokenError, ValueError):
        return None
    if payload.get("type") != "access":
        return None
    database = PostgreSQLAdapter()
    await database.initialize()
    try:
        user = await database.get_user_by_id(payload.get("user_id"))
        if not user or not user.get("is_active"):
            return None
        return [r["name"] for r in await database.get_user_roles(user["id"])]
    finally:
        await database.close()


async def require_quality_admin(request: Request, api_key: Optional[str] = Security(admin_api_key_header)) -> str:
    if api_key and settings.ADMIN_ENDPOINTS_ENABLED and settings.ADMIN_API_KEY:
        if secrets.compare_digest(api_key, settings.ADMIN_API_KEY):
            return "api_key"
    try:
        roles = await roles_from_session(request)
    except HTTPException:
        raise
    except Exception as error:  # noqa: BLE001 - un fallo de la base de datos nunca concede acceso
        logger.warning("quality_admin_denied reason=error error_type=%s", type(error).__name__)
        roles = None
    if roles and ADMIN_ROLE in roles:
        return "role"
    # Motivo del rechazo sin datos personales ni el token: diagnostica sesiones que "no se guardan".
    if not request.cookies.get("access_token"):
        reason = "no_cookie"
    elif roles is None:
        reason = "invalid_or_unknown_session"
    else:
        reason = "not_admin"
    logger.warning("quality_admin_denied reason=%s", reason)
    raise HTTPException(status_code=403, detail="Admin credentials required")
