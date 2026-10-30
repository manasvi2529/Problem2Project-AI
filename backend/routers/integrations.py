"""
ProblemPilot AI — Integrations Router
Manages external integrations: GitHub OAuth lifecycle, token encryption at rest,
Vercel and Render cloud verification, and deployment history tracking.
"""
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from backend.database import get_db
from backend.routers.auth import get_user_from_token
from backend.models.user import User
from backend.models.audit import AuditLog
from backend.models.deployment import Deployment
from backend.config import settings
from backend.services.github_service import GitHubService
from backend.services.cloud_deployer import CloudDeployer
from backend.security import generate_oauth_state, verify_oauth_state

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/integrations", tags=["integrations"])


@router.get("/status")
async def get_integrations_status(
    user: Optional[User] = Depends(get_user_from_token),
):
    """
    Get live configuration and connection status for all external providers.
    Surfaces the exact callback URL as single source of truth.
    """
    missing_github = settings.get_missing_github_oauth_vars()
    missing_vercel = settings.get_missing_vercel_vars()

    is_gh_connected = bool(user and user.github_access_token)
    return {
        "callback_url": settings.GITHUB_REDIRECT_URI,
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
            "oauth_enabled": len(missing_github) == 0,
            "missing_vars": missing_github,
            "connected": is_gh_connected,
            "status": "connected" if is_gh_connected else ("not_configured" if missing_github else "not_connected"),
            "username": user.github_username if user else None,
            "connected_at": user.github_connected_at.isoformat() if (user and user.github_connected_at) else None,
            "callback_url": settings.GITHUB_REDIRECT_URI,
        },
        "cloud": {
            "vercel": {
                **CloudDeployer.get_provider_details("vercel"),
                "missing_vars": missing_vercel,
                "status": "connected" if settings.vercel_configured else "not_configured",
            },
            "render": {
                **CloudDeployer.get_provider_details("render"),
                "status": "connected" if settings.render_configured else "not_configured",
            },
            "docker": CloudDeployer.get_provider_details("docker"),
        },
    }


@router.get("/github/authorize")
async def authorize_github(
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate GitHub OAuth authorization URL with cryptographic HMAC CSRF state.
    """
    missing = settings.get_missing_github_oauth_vars()
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"GitHub OAuth client is not fully configured. Missing required variables: {', '.join(missing)}.",
        )

    # Generate tamper-proof HMAC CSRF state token bound to user.id
    csrf_state = generate_oauth_state(user.id)
    user.github_oauth_state = csrf_state
    await db.commit()

    oauth_info = GitHubService.get_oauth_authorization_url(csrf_state)
    return oauth_info


@router.get("/github/callback")
async def github_oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Handle GitHub OAuth callback, validate HMAC CSRF state token, exchange code,
    and persist credentials securely encrypted at rest.
    """
    if error:
        err_msg = error_description or error
        logger.warning(f"GitHub OAuth reported error: {err_msg}")
        return RedirectResponse(url=f"/#/integrations?github_error={err_msg}")

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing required OAuth callback parameters (code/state).")

    # Validate HMAC signature and expiration on state token
    valid_user_id = verify_oauth_state(state)
    if not valid_user_id:
        logger.warning("GitHub OAuth callback rejected: Invalid or expired HMAC state token.")
        return RedirectResponse(url="/#/integrations?github_error=invalid_state")

    # Locate user matching the verified state
    result = await db.execute(select(User).where(User.id == valid_user_id))
    user = result.scalar_one_or_none()
    if not user or user.github_oauth_state != state:
        logger.warning("GitHub OAuth state mismatch in database.")
        return RedirectResponse(url="/#/integrations?github_error=state_mismatch")

    # Exchange code for access token
    exchange_res = await GitHubService.exchange_code_for_token(code)
    if not exchange_res.get("success"):
        logger.error(f"GitHub token exchange failure: {exchange_res.get('error')}")
        return RedirectResponse(url="/#/integrations?github_error=exchange_failed")

    access_token = exchange_res.get("access_token")
    user_info = exchange_res.get("user", {})

    from datetime import datetime, timezone
    # Store token securely encrypted at rest using AES-256/Fernet
    user.set_github_token(access_token)
    user.github_username = user_info.get("username", "")
    user.github_connected_at = datetime.now(timezone.utc)
    user.github_oauth_state = None  # Consume single-use state token

    log = AuditLog(
        user_id=user.id,
        action="github_oauth_connected",
        category="integrations",
        description=f"GitHub OAuth successfully connected for account @{user.github_username}",
    )
    db.add(log)
    await db.commit()

    return RedirectResponse(url="/#/integrations?github_connected=true")


@router.get("/github/test")
async def test_github_connection(
    user: User = Depends(get_user_from_token),
):
    """
    Test authenticated GitHub connection using user's stored encrypted token.
    Never exposes raw token in response.
    """
    token = user.get_github_token()
    if not token:
        return {
            "connected": False,
            "status": "not_connected",
            "message": "No GitHub account currently linked to this profile.",
        }

    verification = await GitHubService.verify_github_token(token)
    if verification.get("valid"):
        return {
            "connected": True,
            "status": "connected",
            "username": verification.get("username"),
            "name": verification.get("name"),
            "email": verification.get("email"),
            "public_repos": verification.get("public_repos"),
            "scopes": verification.get("scopes"),
            "message": f"Successfully verified connection to GitHub account @{verification.get('username')}.",
        }
    else:
        return {
            "connected": False,
            "status": "connection_expired",
            "error": verification.get("error", "GitHub API rejected current token."),
            "message": "GitHub connection has expired or been revoked. Please reconnect.",
        }


@router.delete("/github")
async def disconnect_github(
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """
    Disconnect GitHub account from user profile and revoke credentials.
    """
    old_username = user.github_username
    user.github_access_token = None
    user.github_username = None
    user.github_connected_at = None
    user.github_oauth_state = None

    log = AuditLog(
        user_id=user.id,
        action="github_disconnected",
        category="integrations",
        description=f"GitHub connection revoked for user: {old_username or 'unknown'}",
    )
    db.add(log)
    await db.commit()
    return {"message": "GitHub account successfully disconnected"}


@router.get("/vercel/verify")
async def verify_vercel_connection(
    user: User = Depends(get_user_from_token),
):
    """
    Validate configured Vercel credentials against live Vercel API.
    """
    return await CloudDeployer.verify_vercel_token()


@router.get("/render/verify")
async def verify_render_connection(
    user: User = Depends(get_user_from_token),
):
    """
    Validate configured Render credentials against live Render API.
    """
    return await CloudDeployer.verify_render_token()


@router.get("/deployments")
async def list_deployment_history(
    project_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """
    List cloud deployment history for user or specific project.
    """
    query = select(Deployment).where(Deployment.owner_id == user.id)
    if project_id:
        query = query.where(Deployment.project_id == project_id)
    query = query.order_by(desc(Deployment.created_at)).limit(limit)

    res = await db.execute(query)
    deployments = res.scalars().all()
    return {"deployments": [d.to_dict() for d in deployments]}
