"""
Authentication router — register, login, profile, mode switching.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr, Field

from backend.database import get_db
from backend.security import hash_password, verify_password, create_access_token, decode_access_token
from backend.models.user import User
from backend.models.audit import AuditLog

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = ""

class LoginRequest(BaseModel):
    email: str
    password: str

class ModeRequest(BaseModel):
    mode: str = Field(..., pattern="^(autonomous|guided|hybrid)$")

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


# ── Helpers ──────────────────────────────────────────────────────────────────

async def get_user_from_token(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """Extract user from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = auth.split(" ", 1)[1]
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Check existing
    existing = await db.execute(
        select(User).where((User.email == body.email) | (User.username == body.username))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email or username already registered")

    user = User(
        email=body.email,
        username=body.username,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
    )
    db.add(user)

    # Audit log
    log = AuditLog(user_id=user.id, action="register", category="auth", description=f"User registered: {body.username}")
    db.add(log)

    await db.commit()
    await db.refresh(user)

    token = create_access_token({"sub": user.id})
    return TokenResponse(access_token=token, user=user.to_dict())


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    # Audit log
    log = AuditLog(user_id=user.id, action="login", category="auth", description="User logged in")
    db.add(log)
    await db.commit()

    token = create_access_token({"sub": user.id})
    return TokenResponse(access_token=token, user=user.to_dict())


@router.get("/me")
async def get_profile(user: User = Depends(get_user_from_token)):
    return {"user": user.to_dict()}


@router.put("/mode")
async def set_mode(
    body: ModeRequest,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    old_mode = user.operating_mode
    user.operating_mode = body.mode
    log = AuditLog(
        user_id=user.id, action="switch_mode", category="settings",
        description=f"Mode changed: {old_mode} → {body.mode}",
    )
    db.add(log)
    await db.commit()
    await db.refresh(user)
    return {"user": user.to_dict(), "message": f"Operating mode set to {body.mode}"}


@router.get("/status")
async def auth_status():
    """Public endpoint to check if API is running."""
    return {"status": "ok", "service": "Problem2Project AI"}
