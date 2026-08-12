import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field

from repository import TaskRepository

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
security = HTTPBearer(auto_error=False)
repo = TaskRepository()

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "change-me")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


class AuthPayload(BaseModel):
    email: str = Field(..., min_length=5, description="User email address")
    password: str = Field(..., min_length=8, description="User password")


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(user_id: int, email: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    jti = str(uuid.uuid4())
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": expire,
        "jti": jti,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    token = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    repo.store_refresh_token(user_id, token, expires_at)
    return token


def decode_access_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if "sub" not in payload or "jti" not in payload:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    return payload


def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)) -> Dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Access token required")

    token = credentials.credentials
    payload = decode_access_token(token)
    jti = payload.get("jti")
    if jti is None or repo.is_token_revoked(jti):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = repo.get_user_by_id(int(payload["sub"]))
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return {"user": user, "token": token, "payload": payload}
