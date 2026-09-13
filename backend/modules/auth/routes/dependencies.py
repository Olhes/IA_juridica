from fastapi import Depends, HTTPException, status
from typing import Annotated, List
from ..services.security import AuthService, oauth2_scheme
from database.postgres_adapter_final import PostgreSQLAdapter


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> dict:
    """
    Dependency para proteger rutas que requieren autenticación.
    Extrae y valida el usuario desde el token JWT en el header Authorization.
    
    Uso:
        @router.get("/protected")
        async def protected_route(current_user: dict = Depends(get_current_user)):
            return {"user": current_user}
    """
    security_service = AuthService()
    try:
        payload = security_service.decode_token(token, is_refresh=False)
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token no válido"
            )
        return payload
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No se pudo validar las credenciales"
        )


async def get_current_active_user(current_user: dict = Depends(get_current_user)) -> dict:
    """
    Dependency para obtener el usuario actual activo.
    Verifica si el usuario está activo en la base de datos.
    """
    db = PostgreSQLAdapter()
    user = await db.get_user_by_id(current_user.get("user_id"))
    
    if not user or not user.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo o no encontrado"
        )
    
    return current_user


async def require_permission(permission: str):
    """
    Dependency factory para verificar permisos específicos.
    
    Uso:
        @router.get("/admin")
        async def admin_route(current_user: dict = Depends(require_permission("admin:system"))):
            return {"message": "Acceso concedido"}
    """
    async def check_permission(current_user: dict = Depends(get_current_active_user)) -> dict:
        db = PostgreSQLAdapter()
        user_id = current_user.get("user_id")
        
        has_perm = await db.has_permission(user_id, permission)
        
        if not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permiso requerido: {permission}"
            )
        
        return current_user
    
    return check_permission


async def require_any_permission(*permissions: str):
    """
    Dependency factory para verificar que el usuario tenga al menos uno de los permisos.
    
    Uso:
        @router.get("/documents")
        async def documents_route(current_user: dict = Depends(require_any_permission("documents:read", "documents:manage"))):
            return {"message": "Acceso concedido"}
    """
    async def check_permissions(current_user: dict = Depends(get_current_active_user)) -> dict:
        db = PostgreSQLAdapter()
        user_id = current_user.get("user_id")
        
        user_permissions = await db.get_user_permissions(user_id)
        
        if not any(perm in user_permissions for perm in permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Se requiere uno de estos permisos: {', '.join(permissions)}"
            )
        
        return current_user
    
    return check_permissions


async def require_role(*roles: str):
    """
    Dependency factory para verificar que el usuario tenga al menos uno de los roles.
    
    Uso:
        @router.get("/lawyer-only")
        async def lawyer_route(current_user: dict = Depends(require_role("lawyer", "admin"))):
            return {"message": "Acceso concedido"}
    """
    async def check_roles(current_user: dict = Depends(get_current_active_user)) -> dict:
        user_roles = current_user.get("roles", [])
        
        if not any(role in user_roles for role in roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Se requiere uno de estos roles: {', '.join(roles)}"
            )
        
        return current_user
    
    return check_roles


# Type hints para usar en las rutas
CurrentUser = Annotated[dict, Depends(get_current_user)]
CurrentActiveUser = Annotated[dict, Depends(get_current_active_user)]
