"""
Approvals router — manage approval requests and workflow states.
Backend-enforced approval engine.
"""
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field

from backend.database import get_db
from backend.routers.auth import get_user_from_token
from backend.models.user import User
from backend.models.approval import Approval, WorkflowState
from backend.models.audit import AuditLog

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class ApprovalDecision(BaseModel):
    decision: str = Field(..., pattern="^(approved|rejected|modified)$")
    reason: Optional[str] = ""
    feedback: Optional[str] = ""  # Frontend alias support
    modifications: Optional[dict] = {}


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("")
async def list_approvals(
    status: str = None,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """List approval requests for the current user."""
    query = select(Approval).where(Approval.owner_id == user.id)
    if status:
        query = query.where(Approval.decision == status)
    query = query.order_by(Approval.created_at.desc())

    result = await db.execute(query)
    approvals = result.scalars().all()
    return {"approvals": [a.to_dict() for a in approvals]}


@router.get("/pending")
async def list_pending_approvals(
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get all pending approval requests."""
    result = await db.execute(
        select(Approval)
        .where(Approval.owner_id == user.id, Approval.decision == "pending")
        .order_by(Approval.created_at.desc())
    )
    approvals = result.scalars().all()
    return {
        "pending_count": len(approvals),
        "approvals": [a.to_dict() for a in approvals],
    }


@router.get("/{approval_id}")
async def get_approval(
    approval_id: str,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Approval).where(Approval.id == approval_id, Approval.owner_id == user.id)
    )
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    return {"approval": approval.to_dict()}


@router.post("/{approval_id}/decide")
@router.post("/{approval_id}/respond")
async def decide_approval(
    approval_id: str,
    body: ApprovalDecision,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Approve, reject, or modify an approval request."""
    result = await db.execute(
        select(Approval).where(Approval.id == approval_id, Approval.owner_id == user.id)
    )
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")

    if approval.decision != "pending":
        raise HTTPException(status_code=409, detail=f"Approval already decided: {approval.decision}")

    approval.decision = body.decision
    approval.decision_reason = body.reason or body.feedback or ""
    approval.modifications = body.modifications or {}
    approval.decided_at = datetime.now(timezone.utc)

    # Audit log
    log = AuditLog(
        user_id=user.id,
        project_id=approval.project_id,
        action=f"approval_{body.decision}",
        category="approval",
        description=f"{body.decision}: {approval.title}",
        details={"approval_id": approval_id, "action_type": approval.action_type},
    )
    db.add(log)
    await db.commit()
    await db.refresh(approval)

    return {
        "approval": approval.to_dict(),
        "message": f"Approval {body.decision}",
    }


# ── Workflow State ───────────────────────────────────────────────────────────

@router.get("/workflows/{entity_type}/{entity_id}")
async def get_workflow_state(
    entity_type: str,
    entity_id: str,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WorkflowState).where(
            WorkflowState.entity_type == entity_type,
            WorkflowState.entity_id == entity_id,
            WorkflowState.owner_id == user.id,
        )
    )
    wf = result.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"workflow": wf.to_dict()}
