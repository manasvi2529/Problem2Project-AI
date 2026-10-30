"""
ProblemPilot AI — Security utilities (JWT + password hashing)
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.config import settings
from backend.database import get_db

import bcrypt
import base64
import hashlib
import hmac
import secrets
import logging
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

security_scheme = HTTPBearer(auto_error=False)


def get_encryption_fernet() -> Fernet:
    """Derive deterministic 32-byte Fernet key from GITHUB_TOKEN_ENCRYPTION_KEY or SECRET_KEY."""
    raw_key = settings.GITHUB_TOKEN_ENCRYPTION_KEY or settings.SECRET_KEY
    derived_32 = hashlib.sha256(raw_key.encode("utf-8")).digest()
    b64_key = base64.urlsafe_b64encode(derived_32)
    return Fernet(b64_key)


def encrypt_credential(plain_text: str) -> str:
    """Encrypt a sensitive token or credential for secure storage at rest."""
    if not plain_text:
        return ""
    try:
        f = get_encryption_fernet()
        encrypted = f.encrypt(plain_text.encode("utf-8")).decode("utf-8")
        return f"enc:v1:{encrypted}"
    except Exception as e:
        logger.error(f"Error encrypting credential: {e}")
        return plain_text


def decrypt_credential(cipher_text: str) -> str:
    """Decrypt a stored credential. Supports transparent migration for existing plaintext tokens."""
    if not cipher_text:
        return ""
    if not cipher_text.startswith("enc:v1:"):
        # Legacy/plaintext token; return directly (will be encrypted on next save)
        return cipher_text
    raw_cipher = cipher_text[len("enc:v1:"):]
    try:
        f = get_encryption_fernet()
        return f.decrypt(raw_cipher.encode("utf-8")).decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to decrypt credential: {e}")
        return ""


def generate_oauth_state(user_id: str) -> str:
    """Generate tamper-proof CSRF state token bound to user_id with HMAC signature."""
    state_secret = settings.GITHUB_OAUTH_STATE_SECRET or settings.SECRET_KEY
    nonce = secrets.token_hex(16)
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    payload = f"{user_id}:{timestamp}:{nonce}"
    sig = hmac.new(state_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    return f"{payload}:{sig}"


def verify_oauth_state(state_token: str, max_age_seconds: int = 600) -> Optional[str]:
    """Verify HMAC signature and age of state token. Returns user_id if valid, None if invalid or expired."""
    try:
        parts = state_token.split(":")
        if len(parts) != 4:
            return None
        user_id, timestamp_str, nonce, sig = parts
        state_secret = settings.GITHUB_OAUTH_STATE_SECRET or settings.SECRET_KEY
        payload = f"{user_id}:{timestamp_str}:{nonce}"
        expected_sig = hmac.new(state_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(sig, expected_sig):
            return None
        # Check expiry
        ts = int(timestamp_str)
        now = int(datetime.now(timezone.utc).timestamp())
        if now - ts > max_age_seconds:
            return None
        return user_id
    except Exception:
        return None


def hash_password(password: str) -> str:
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        pwd_bytes = plain_password.encode("utf-8")[:72]
        hashed_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hashed_bytes)
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Dependency: extract current user from JWT token."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    from backend.models.user import User
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
