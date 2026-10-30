"""
ProblemPilot AI — Integrations Router
Manages external integrations: GitHub OAuth lifecycle, cloud hosting providers,
search adapters, and system health status.
"""
import uuid
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_db
from backend.routers.auth import get_user_from_token
from backend.models.user import User
from backend.models.audit import AuditLog
from backend.config import settings
from backend.services.github_service import GitHubService
from backend.services.cloud_deployer import CloudDeployer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/integrations", tags=["integrations"])


@router.get("/status")
async def get_integrations_status(
    user: Optional[User] = Depends(get_user_from_token),
):
    """
    Get live configuration and connection status for all external providers.
    """
    return {
        "ai": {
            "configured": settings.ai_configured,
            "provider": settings.AI_PROVIDER,
            "model": settings.OPENROUTER_MODEL if settings.AI_PROVIDER == "openrouter" else "default",
        },
        "search": {
            "configured": settings.search_configured,
            "provider": settings.SEARCH_PROVIDER,
        },
        "github": {
            "configured": settings.github_configured,
            "oauth_enabled": bool(settings.GITHUB_CLIENT_ID and settings.GITHUB_CLIENT_SECRET),
            "connected": bool(user and user.github_access_token),
            "username": user.github_username if user else None,
            "connected_at": user.github_connected_at.isoformat() if (user and user.github_connected_at) else None,
        },
        "cloud": {
            "vercel": CloudDeployer.get_provider_details("vercel"),
            "render": CloudDeployer.get_provider_details("render"),
            "docker": CloudDeployer.get_provider_details("docker"),
        },
    }


@router.get("/github/authorize")
async def authorize_github(
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate GitHub OAuth authorization URL with cryptographic CSRF state.
    """
    if not settings.GITHUB_CLIENT_ID:
        raise HTTPException(
            status_code=503,
            detail="GitHub OAuth client is not configured. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET in .env.",
        )

    # Generate random CSRF token
    csrf_state = str(uuid.uuid4())
    user.github_oauth_state = csrf_state
    await db.commit()

    oauth_info = GitHubService.get_oauth_authorization_url(csrf_state)
    return oauth_info


@router.get("/github/callback")
async def github_oauth_callback(
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Handle GitHub OAuth callback, validate CSRF state token, exchange code,
    and persist credentials securely.
    """
    if error:
        logger.warning(f"GitHub OAuth reported error: {error}")
        return RedirectResponse(url="/#/integrations?github_error=" + error)

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing required OAuth callback parameters.")

    # Locate user with matching CSRF state
    result = await db.execute(select(User).where(User.github_oauth_state == state))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=403, detail="Invalid or expired OAuth state token (CSRF validation failed).")

    # Exchange code for access token
    exchange_res = await GitHubService.exchange_code_for_token(code)
    if not exchange_res.get("success"):
        logger.error(f"GitHub token exchange failure: {exchange_res.get('error')}")
        return RedirectResponse(url="/#/integrations?github_error=exchange_failed")

    access_token = exchange_res.get("access_token")
    user_info = exchange_res.get("user", {})

    from datetime import datetime, timezone
    user.github_access_token = access_token
    user.github_username = user_info.get("username", "")
    user.github_connected_at = datetime.now(timezone.utc)
    user.github_oauth_state = None  # Consume state token

    log = AuditLog(
        user_id=user.id,
        action="github_oauth_connected",
        category="integrations",
        description=f"GitHub OAuth connected for username: {user.github_username}",
    )
    db.add(log)
    await db.commit()

    return RedirectResponse(url="/#/integrations?github_connected=true")


@router.delete("/github")
async def disconnect_github(
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """
    Disconnect GitHub account from user profile.
    """
    user.github_access_token = None
    user.github_username = None
    user.github_connected_at = None

    log = AuditLog(
        user_id=user.id,
        action="github_disconnected",
        category="integrations",
        description="GitHub connection revoked",
    )
    db.add(log)
    await db.commit()
    return {"message": "GitHub account successfully disconnected"}

