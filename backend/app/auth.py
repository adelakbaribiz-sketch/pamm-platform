from datetime import datetime, timedelta, timezone
from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db
from .models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=True)

def hash_password(p: str) -> str: return pwd_context.hash(p)
def verify_password(p: str, h: str) -> bool: return pwd_context.verify(p, h)

def create_access_token(user_id: str, role: str, tenant_id: str | None) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_ttl_min)
    return jwt.encode(
        {"sub": user_id, "role": role, "tenant_id": tenant_id, "exp": exp, "type": "access"},
        settings.jwt_secret, algorithm=settings.jwt_alg,
    )

def create_refresh_token(user_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_ttl_days)
    return jwt.encode(
        {"sub": user_id, "exp": exp, "type": "refresh"},
        settings.jwt_secret, algorithm=settings.jwt_alg,
    )

def decode_token(tok: str) -> dict:
    return jwt.decode(tok, settings.jwt_secret, algorithms=[settings.jwt_alg])

class Principal:
    def __init__(self, user_id: str, role: str, tenant_id: str | None, email: str):
        self.user_id = user_id
        self.role = role
        self.tenant_id = tenant_id
        self.email = email
    @property
    def is_super_admin(self) -> bool: return self.role == "super_admin"
    def has_role(self, *roles: str) -> bool: return self.role in roles

def get_principal(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> Principal:
    cred_err = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise cred_err
        user_id = payload["sub"]
        role = payload["role"]
        tenant_id = payload.get("tenant_id")
    except JWTError:
        raise cred_err
    user = db.query(User).filter(User.id == user_id, User.status == "active").first()
    if not user:
        raise cred_err
    return Principal(user_id=user.id, role=role, tenant_id=user.tenant_id, email=user.email)

def require_roles(*roles: str):
    def _dep(p: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if p.is_super_admin or p.has_role(*roles):
            return p
        raise HTTPException(status_code=403, detail="Insufficient role")
    return _dep
