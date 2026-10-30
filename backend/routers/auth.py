"""
Authentication router — register, login, profile, mode switching, settings.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from typing import Optional, Any, Dict

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
    full_name: Optional[str] = ""
    name: Optional[str] = ""  # Frontend alias support


class LoginRequest(BaseModel):
    email: str
    password: str


class ModeRequest(BaseModel):
    mode: Optional[str] = None
    operating_mode: Optional[str] = None  # Frontend alias support


class SettingsUpdateRequest(BaseModel):
    operating_mode: Optional[str] = None
    mode: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None


class TokenResponse(BaseModel):
    access_token: str
    token: str  # Frontend alias
    token_type: str = "bearer"
    user: dict


# ── Helpers ──────────────────────────────────────────────────────────────────

async def get_user_from_token(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """Extract user from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = auth.split(" ", 1)[1].strip()
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
    # Basic email format check
    clean_email = body.email.strip().lower()
    if "@" not in clean_email or "." not in clean_email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Invalid email format")

    # Check existing
    existing = await db.execute(
        select(User).where((User.email == clean_email) | (User.username == body.username.strip()))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email or username already registered")

    display_name = (body.full_name or body.name or body.username).strip()

    import uuid
    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        email=clean_email,
        username=body.username.strip(),
        hashed_password=hash_password(body.password),
        full_name=display_name,
        operating_mode="hybrid",
    )
    db.add(user)

    # Audit log
    log = AuditLog(
        user_id=user_id,
        action="register",
        category="auth",
        description=f"User registered: {user.username}",
    )
    db.add(log)

    await db.commit()
    await db.refresh(user)

    token = create_access_token({"sub": user.id})
    return TokenResponse(
        access_token=token,
        token=token,
        user=user.to_dict(),
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    clean_email = body.email.strip().lower()
    result = await db.execute(select(User).where(User.email == clean_email))
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
    return TokenResponse(
        access_token=token,
        token=token,
        user=user.to_dict(),
    )


@router.get("/me")
async def get_profile(user: User = Depends(get_user_from_token)):
    user_dict = user.to_dict()
    return {"user": user_dict, **user_dict}


@router.put("/mode")
async def set_mode(
    body: ModeRequest,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    selected_mode = (body.mode or body.operating_mode or "").lower()
    if selected_mode not in ("autonomous", "guided", "hybrid"):
        raise HTTPException(status_code=400, detail="Invalid mode. Must be autonomous, guided, or hybrid")

    old_mode = user.operating_mode
    user.operating_mode = selected_mode
    log = AuditLog(
        user_id=user.id,
        action="switch_mode",
        category="settings",
        description=f"Mode changed: {old_mode} → {selected_mode}",
    )
    db.add(log)
    await db.commit()
    await db.refresh(user)
    return {"user": user.to_dict(), "operating_mode": selected_mode, "message": f"Operating mode set to {selected_mode}"}


@router.put("/settings")
async def update_settings(
    body: SettingsUpdateRequest,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Handle settings updates from frontend."""
    selected_mode = body.operating_mode or body.mode
    if selected_mode:
        selected_mode = selected_mode.lower()
        if selected_mode in ("autonomous", "guided", "hybrid"):
            user.operating_mode = selected_mode

    if body.preferences is not None:
        current_prefs = user.preferences or {}
        current_prefs.update(body.preferences)
        user.preferences = current_prefs

    log = AuditLog(
        user_id=user.id,
        action="update_settings",
        category="settings",
        description="User settings updated",
    )
    db.add(log)
    await db.commit()
    await db.refresh(user)
    return {"user": user.to_dict(), "operating_mode": user.operating_mode, "message": "Settings updated"}


@router.get("/status")
async def auth_status():
    """Public endpoint to check if API is running."""
    return {"status": "ok", "service": "ProblemPilot AI"}
