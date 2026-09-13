from fastapi import HTTPException, status
from .security import AuthService as SecurityService
from database.postgres_adapter_final import PostgreSQLAdapter


class AuthService:
    def __init__(self):
        self.db = PostgreSQLAdapter()
        self.security = SecurityService()
    
    async def authenticate_user(self, username: str, password: str):
        """
        Autentica un usuario usando username (email) y password.
        Retorna access_token y refresh_token.
        """
        # Buscar usuario en PostgreSQL
        user = await self.db.get_user_by_email(username)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales incorrectas",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Verificar password
        if not self.security.verify_password(password, user['password_hash']):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales incorrectas",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Actualizar último login
        await self.db.update_last_login(user['id'])
        
        # Obtener roles del usuario
        roles = await self.db.get_user_roles(user['id'])
        role_names = [r['name'] for r in roles]
        
        # Crear payload del token
        payload = {
            "sub": user['email'],
            "user_id": user['id'],
            "username": user['username'],
            "role": role_names[0] if role_names else user.get('role', 'user'),
            "roles": role_names
        }
        
        access_token = self.security.create_access_token(payload)
        refresh_token = self.security.create_refresh_token(payload)
        
        return access_token, refresh_token

    async def refresh_access_token(self, refresh_token: str):
        """
        Renueva el access token usando un refresh token válido.
        """
        try:
            payload = self.security.decode_token(refresh_token, is_refresh=True)
            
            # Verificar que el usuario aún existe y está activo
            user = await self.db.get_user_by_email(payload.get("sub"))
            if not user or not user.get('is_active'):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Usuario no válido o inactivo"
                )
            
            # Obtener roles actualizados
            roles = await self.db.get_user_roles(user['id'])
            role_names = [r['name'] for r in roles]
            
            # Crear nuevo payload con roles actualizados
            new_payload = {
                "sub": user['email'],
                "user_id": user['id'],
                "username": user['username'],
                "role": role_names[0] if role_names else user.get('role', 'user'),
                "roles": role_names
            }
            
            new_access_token = self.security.create_access_token(new_payload)
            return new_access_token
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token inválido o expirado"
            )