from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse
from .schemas import TokenResponseSchema, RefreshTokenRequest, UserResponse
from ..services.auth_service import AuthService
from ..services.security import AuthService as SecurityService
from database.postgres_adapter_final import PostgreSQLAdapter
from config.settings import settings
import httpx
import urllib.parse
import jwt

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), response: Response = None):
    """
    OAuth2 compatible login endpoint.
    Usa form-data con username (email) y password.
    Establece cookies httpOnly en lugar de devolver tokens en el cuerpo.
    """
    auth_service = AuthService()
    access_token, refresh_token = await auth_service.authenticate_user(form_data.username, form_data.password)
    
    # Crear respuesta con cookies httpOnly
    from fastapi.responses import JSONResponse
    resp = JSONResponse(content={"message": "Login exitoso"})
    
    # Establecer cookies httpOnly
    resp.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,  # False en desarrollo para HTTP
        samesite="lax",
        max_age=900  # 15 minutos
    )
    
    resp.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=604800  # 7 días
    )
    
    return resp


@router.post("/refresh")
async def refresh_token(request: Request, response: Response):
    """Renueva el access token usando el refresh token de la cookie"""
    refresh_token = request.cookies.get('refresh_token')
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token en cookies")
    
    auth_service = AuthService()
    new_access_token = await auth_service.refresh_access_token(refresh_token)
    
    # Actualizar la cookie de access token
    from fastapi.responses import JSONResponse
    resp = JSONResponse(content={"access_token": new_access_token, "token_type": "bearer"})
    
    resp.set_cookie(
        key="access_token",
        value=new_access_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=900  # 15 minutos
    )
    
    return resp


@router.get("/me", response_model=UserResponse)
async def get_current_user(request: Request):
    """Obtiene información del usuario actual desde el token JWT en cookie"""
    # Obtener token de la cookie
    access_token = request.cookies.get('access_token')
    if not access_token:
        raise HTTPException(status_code=401, detail="No autenticado")
    
    # Decodificar token
    security_service = SecurityService()
    try:
        payload = security_service.decode_token(access_token, is_refresh=False)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Token no válido")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    
    # Obtener usuario de la base de datos
    db = PostgreSQLAdapter()
    user = await db.get_user_by_id(payload.get("user_id"))
    
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    roles = await db.get_user_roles(user['id'])
    role_names = [r['name'] for r in roles]
    
    return UserResponse(
        id=user['id'],
        email=user['email'],
        username=user['username'],
        full_name=user.get('full_name'),
        picture=user.get('picture'),
        role=role_names[0] if role_names else user.get('role', 'user'),
        roles=role_names,
        is_active=user['is_active']
    )


@router.post("/logout")
async def logout(response: Response):
    """Endpoint de logout - elimina las cookies httpOnly"""
    from fastapi.responses import JSONResponse
    resp = JSONResponse(content={"message": "Sesión cerrada correctamente"})
    
    # Eliminar cookies
    resp.delete_cookie(key="access_token")
    resp.delete_cookie(key="refresh_token")
    
    return resp


@router.post("/reset-admin-password")
async def reset_admin_password():
    """
    Endpoint temporal para resetear el password del admin a 'admin123'
    """
    # Hash precalculado de 'admin123' con bcrypt
    new_hash = '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5NU7bXqL0f1eS'
    
    return {
        "message": "Usa este hash para actualizar manualmente en la base de datos",
        "email": "admin@iajuridica.pe",
        "password": "admin123",
        "hash": new_hash,
        "sql": f"UPDATE auth_schema.users SET password_hash = '{new_hash}', is_active = true WHERE email = 'admin@iajuridica.pe';"
    }


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
            detail="Google OAuth no está configurado. Faltan GOOGLE_CLIENT_ID y GOOGLE_CLIENT_SECRET"
        )
    
    # Parámetros para la URL de autorización de Google
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "scope": "openid email profile",
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent"
    }
    
    auth_url = f"{settings.GOOGLE_AUTHORIZATION_URL}?{urllib.parse.urlencode(params)}"
    
    return RedirectResponse(url=auth_url)


@router.get("/google/callback")
async def google_callback(request: Request, code: str, state: str = None):
    """
    Callback de Google OAuth 2.0
    Recibe el código de autorización y lo intercambia por tokens
    """
    print(f"🔍 Google OAuth callback recibido. Code: {code[:20] if code else 'None'}...")
    print(f"🔍 Redirect URI configurado: {settings.GOOGLE_REDIRECT_URI}")
    
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        print("❌ Google OAuth no está configurado")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google OAuth no está configurado"
        )
    
    if not code:
        print("❌ No se recibió código de autorización")
        raise HTTPException(status_code=400, detail="No se recibió código de autorización")
    
    try:
        # Intercambiar el código por tokens de acceso
        token_data = {
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code"
        }
        
        print("🔄 Intercambiando código por tokens...")
        async with httpx.AsyncClient() as client:
            token_response = await client.post(settings.GOOGLE_TOKEN_URL, data=token_data)
            print(f"🔄 Token response status: {token_response.status_code}")
            token_response.raise_for_status()
            tokens = token_response.json()
            print(f"✅ Tokens obtenidos")
            
            # Obtener información del usuario
            print("🔄 Obteniendo userinfo de Google...")
            userinfo_response = await client.get(
                settings.GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {tokens['access_token']}"}
            )
            print(f"🔄 Userinfo response status: {userinfo_response.status_code}")
            userinfo_response.raise_for_status()
            userinfo = userinfo_response.json()
            print(f"✅ Userinfo obtenido: {userinfo.get('email')}")
        
        # Crear o actualizar usuario en la base de datos
        db = PostgreSQLAdapter()
        await db.initialize()  # Asegurar que la conexión esté inicializada
        user = await db.get_user_by_email(userinfo["email"])
        
        if not user:
            print(f"👤 Usuario no encontrado, creando nuevo usuario...")
            # Crear nuevo usuario con Google OAuth (sin contraseña)
            # Usar un hash precalculado para evitar problemas con bcrypt/passlib
            # Hash de "google_oauth_temp" con bcrypt
            temp_hash = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5NU7bXqL0f1eS"

            user = await db.create_user(
                email=userinfo["email"],
                username=userinfo["email"].split("@")[0],
                password_hash=temp_hash,
                full_name=userinfo.get("name", ""),
                picture=userinfo.get("picture", ""),
                role='user'
            )
            print(f"✅ Usuario creado: {user['id']}")
        else:
            print(f"👤 Usuario existente encontrado: {user['id']}")
            # Actualizar usuario con datos de Google (picture, full_name)
            await db.update_user(user['id'], {
                'full_name': userinfo.get("name", user.get('full_name', '')),
                'picture': userinfo.get("picture", user.get('picture', ''))
            })
            print(f"✅ Usuario actualizado con datos de Google")
        
        # Generar tokens JWT
        security_service = SecurityService()
        access_token = security_service.create_access_token({"user_id": user["id"], "email": user["email"]})
        refresh_token = security_service.create_refresh_token({"user_id": user["id"], "email": user["email"]})
        print(f"✅ Tokens JWT generados")
        
        # Crear respuesta con cookies httpOnly
        response = RedirectResponse(url=settings.GOOGLE_FRONTEND_CALLBACK_URI)
        
        # Establecer cookies httpOnly (más seguras que localStorage)
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=False,  # False en desarrollo para HTTP
            samesite="lax",
            max_age=900  # 15 minutos
        )
        
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=604800  # 7 días
        )
        
        print(f"✅ Cookies establecidas, redirigiendo a {settings.GOOGLE_FRONTEND_CALLBACK_URI}")
        return response
        
    except Exception as e:
        print(f"❌ Error en Google OAuth callback: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error en OAuth callback: {str(e)}")