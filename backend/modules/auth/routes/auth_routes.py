import logging
import json
import secrets

import bcrypt

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse, RedirectResponse
from .schemas import UserResponse
from ..services.auth_service import AuthService
from ..services.security import AuthService as SecurityService
from database.adapter import get_database_adapter
from database.redis_adapter import redis_adapter
from database.surreal_adapter import SurrealAdapter
from config.settings import settings
import httpx
import urllib.parse
import jwt

router = APIRouter(prefix="/auth", tags=["Autenticación"])
logger = logging.getLogger("ia_juridica.auth")

ACCESS_TOKEN_MAX_AGE = 900
REFRESH_TOKEN_MAX_AGE = 604800


def _set_auth_cookies(
    response: Response, access_token: str, refresh_token: str | None = None
) -> None:
    secure = settings.session_cookie_secure()
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=ACCESS_TOKEN_MAX_AGE,
        path="/",
    )
    if refresh_token is not None:
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=secure,
            samesite="lax",
            max_age=REFRESH_TOKEN_MAX_AGE,
            path="/",
        )


@router.post("/login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(), response: Response = None
):
    """
    OAuth2 compatible login endpoint.
    Usa form-data con username (email) y password.
    Establece cookies httpOnly en lugar de devolver tokens en el cuerpo.
    """
    auth_service = AuthService()
    access_token, refresh_token = await auth_service.authenticate_user(
        form_data.username, form_data.password
    )

    resp = JSONResponse(content={"message": "Login exitoso"})
    _set_auth_cookies(resp, access_token, refresh_token)
    return resp


@router.post("/refresh")
async def refresh_token(request: Request, response: Response):
    """Renueva el access token usando el refresh token de la cookie"""
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token en cookies")

    auth_service = AuthService()
    new_access_token = await auth_service.refresh_access_token(refresh_token)

    resp = JSONResponse(
        content={"access_token": new_access_token, "token_type": "bearer"}
    )
    _set_auth_cookies(resp, new_access_token)
    return resp


@router.get("/me", response_model=UserResponse)
async def get_current_user(request: Request):
    """Obtiene información del usuario actual desde el token JWT en cookie con cache en Redis"""
    access_token = request.cookies.get("access_token")
    if not access_token:
        raise HTTPException(status_code=401, detail="No autenticado")

    security_service = SecurityService()
    try:
        payload = security_service.decode_token(access_token, is_refresh=False)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Token no válido")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    user_id = payload.get("user_id")
    cache_key = f"user:{user_id}:profile"
    try:
        # `initialize()` es idempotente: reutiliza la conexión ya abierta.
        await redis_adapter.initialize()
        cached_user = await redis_adapter.get_cache(cache_key)
        if cached_user:
            # `get_cache` ya deserializa el JSON; volver a parsearlo rompía
            # siempre el cache-hit con "the JSON object must be str...".
            user_data = json.loads(cached_user) if isinstance(cached_user, str) else cached_user
            return UserResponse(**user_data)
    except Exception as e:
        logger.warning("Redis cache miss: %s", type(e).__name__)

    db = get_database_adapter(SurrealAdapter)
    await db.initialize()
    user = await db.get_user_by_id(user_id)

    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    roles = await db.get_user_roles(user["id"])
    role_names = [r["name"] for r in roles]

    user_response = UserResponse(
        id=user["id"],
        email=user["email"],
        username=user["username"],
        full_name=user.get("full_name"),
        picture=user.get("picture"),
        role=role_names[0] if role_names else user.get("role", "user"),
        roles=role_names,
        is_active=user["is_active"],
    )

    try:
        await redis_adapter.set_cache(
            cache_key,
            json.dumps(user_response.model_dump()),
            300,
        )
    except Exception as e:
        logger.warning("Redis cache write failed: %s", type(e).__name__)

    return user_response


@router.post("/logout")
async def logout(response: Response):
    """Endpoint de logout - elimina las cookies httpOnly"""
    resp = JSONResponse(content={"message": "Sesión cerrada correctamente"})
    resp.delete_cookie(key="access_token")
    resp.delete_cookie(key="refresh_token")
    return resp


# --- OAuth 2.0 Google Endpoints ---


@router.get("/google")
async def google_login():
    """
    Inicia el flujo OAuth 2.0 con Google
    Redirige al usuario a la página de consentimiento de Google
    """
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google OAuth no está configurado. Faltan GOOGLE_CLIENT_ID y GOOGLE_CLIENT_SECRET",
        )

    # Parámetros para la URL de autorización de Google
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "scope": "openid email profile",
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",
    }

    auth_url = f"{settings.GOOGLE_AUTHORIZATION_URL}?{urllib.parse.urlencode(params)}"

    return RedirectResponse(url=auth_url)


@router.get("/google/callback")
async def google_callback(request: Request, code: str, state: str = None):
    """
    Callback de Google OAuth 2.0
    Recibe el código de autorización y lo intercambia por tokens
    """

    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google OAuth no está configurado",
        )

    if not code:
        raise HTTPException(
            status_code=400, detail="No se recibió código de autorización"
        )

    # Esta etapa va al log: usa solo etiquetas fijas, nunca datos del proveedor.
    stage = "provider_token"
    try:
        # Intercambiar el código por tokens de acceso
        token_data = {
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        }

        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                settings.GOOGLE_TOKEN_URL, data=token_data
            )
            token_response.raise_for_status()
            tokens = token_response.json()

            # Obtener información del usuario
            stage = "provider_profile"
            userinfo_response = await client.get(
                settings.GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            userinfo_response.raise_for_status()
            userinfo = userinfo_response.json()

        # Crear o actualizar usuario en la base de datos
        stage = "initialize"
        db = get_database_adapter(SurrealAdapter)
        await db.initialize()  # Asegurar que la conexión esté inicializada

        stage = "get_user_by_email"
        user = await db.get_user_by_email(userinfo["email"])

        if not user:
            # Crear nuevo usuario con Google OAuth (sin contraseña usable).
            # bcrypt directo (passlib falla con bcrypt>=5) sobre un secreto aleatorio
            # descartado: nadie puede entrar por /auth/login con esta cuenta.
            stage = "prepare_user"
            temp_hash = bcrypt.hashpw(
                secrets.token_urlsafe(32).encode(), bcrypt.gensalt()
            ).decode()

            stage = "create_user"
            user = await db.create_user(
                email=userinfo["email"],
                username=userinfo["email"].split("@")[0],
                password_hash=temp_hash,
                full_name=userinfo.get("name", ""),
                picture=userinfo.get("picture", ""),
                role="user",
            )
        else:
            # Actualizar usuario con datos de Google (picture, full_name)
            stage = "update_user"
            await db.update_user(
                user["id"],
                {
                    "full_name": userinfo.get("name", user.get("full_name", "")),
                    "picture": userinfo.get("picture", user.get("picture", "")),
                },
            )

        # Generar tokens JWT
        stage = "create_session"
        security_service = SecurityService()
        access_token = security_service.create_access_token(
            {"user_id": user["id"], "email": user["email"]}
        )
        refresh_token = security_service.create_refresh_token(
            {"user_id": user["id"], "email": user["email"]}
        )

        response = RedirectResponse(url=settings.GOOGLE_FRONTEND_CALLBACK_URI)
        _set_auth_cookies(response, access_token, refresh_token)
        return response

    except HTTPException:
        raise
    except Exception as e:
        # Provider exceptions may contain authorization codes or token payloads.
        # Keep only safe diagnostics, never exception text or traceback.
        logger.error(
            "oauth_callback_failed stage=%s request_id=%s error_type=%s",
            stage,
            getattr(request.state, "request_id", "unknown"),
            type(e).__name__,
        )
        raise HTTPException(status_code=500, detail="OAuth callback failed")
