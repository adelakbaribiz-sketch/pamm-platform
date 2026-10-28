from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy.orm import Session
from ..auth import verify_password, create_access_token, create_refresh_token, decode_token, get_principal, Principal
from ..db import get_db
from ..models import User
from ..schemas import LoginIn, RefreshIn, TokenOut

router = APIRouter()

@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email, User.status == "active").first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    return TokenOut(
        access_token=create_access_token(user.id, user.role, user.tenant_id),
        refresh_token=create_refresh_token(user.id),
        role=user.role, tenant_id=user.tenant_id, user_id=user.id,
    )

@router.post("/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        user = db.query(User).filter(User.id == payload["sub"], User.status == "active").first()
        if not user: raise HTTPException(status_code=401, detail="User not found")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    return TokenOut(
        access_token=create_access_token(user.id, user.role, user.tenant_id),
        refresh_token=create_refresh_token(user.id),
        role=user.role, tenant_id=user.tenant_id, user_id=user.id,
    )

@router.get("/me")
def me(p: Principal = Depends(get_principal)):
    return {"user_id": p.user_id, "role": p.role, "tenant_id": p.tenant_id, "email": p.email}
