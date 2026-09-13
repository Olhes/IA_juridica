import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CLAVE_SECRETA_DESAROLLO_IA_JURIDICA")
REFRESH_SECRET_KEY = os.getenv("JWT_REFRESH_SECRET_KEY", "CLAVE_REFRESH_DESAROLLO_IA_JURIDICA")
ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme para token en header Authorization: Bearer <token>
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


class AuthService:
    @staticmethod
    def hash_password(password: str) -> str:
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
        to_encode.update({"exp": expire, "type": "access"})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    def create_refresh_token(self, data: Dict[str, Any]) -> str:
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(days=7)
        to_encode.update({"exp": expire, "type": "refresh"})
        return jwt.encode(to_encode, REFRESH_SECRET_KEY, algorithm=ALGORITHM)

    def decode_token(self, token: str, is_refresh: bool = False) -> Dict[str, Any]:
        secret = REFRESH_SECRET_KEY if is_refresh else SECRET_KEY
        return jwt.decode(token, secret, algorithms=[ALGORITHM])

    async def get_current_user(self, token: str = Depends(oauth2_scheme)) -> dict:
        """Dependency para obtener el usuario actual desde el token JWT"""
        try:
            payload = self.decode_token(token, is_refresh=False)
            if payload.get("type") != "access":
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token no válido")
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expirado")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")
