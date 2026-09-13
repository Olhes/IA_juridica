from pydantic import BaseModel, EmailStr
from typing import Optional, List


class LoginSchema(BaseModel):
    email: EmailStr
    password: str


class TokenResponseSchema(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: Optional[str] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    full_name: Optional[str] = None
    picture: Optional[str] = None
    role: str
    roles: List[str] = []
    is_active: bool


class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str
    full_name: Optional[str] = None
    role: str = "user"


class RoleResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None


class PermissionResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    resource: str
    action: str