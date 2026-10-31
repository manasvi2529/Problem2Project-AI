"""
ProblemPilot AI — Permission & Approval Engine
State machine governing protected operations and enforcing operating mode boundaries
(Autonomous, Guided, Hybrid) with persistent audit logs.
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from backend.models.approval import Approval, WorkflowState, compute_params_hash
from backend.models.audit import AuditLog

logger = logging.getLogger(__name__)


# Standard Stages in ProblemPilot AI
STAGES = [
    "prompt_input",
    "live_research",
    "problem_validation",
    "opportunity_selection",
    "project_design",
    "build_workspace",
    "test_verification",
    "github_sync",
    "cloud_deploy",
]

# Protected operations that require an explicit human-in-the-loop approval
PROTECTED_ACTIONS = {
    "select_opportunity": {
        "title": "Select Problem Opportunity",
        "risk_level": "low",
        "description": "Lock in the selected problem as the foundation for the software project.",
    },
    "approve_architecture": {
        "title": "Approve Project Architecture & Tech Stack",
        "risk_level": "medium",
        "description": "Approve system design, database schemas, and API contracts before generating code.",
    },
    "generate_workspace": {
        "title": "Generate Project Source Files",
        "risk_level": "medium",
        "description": "Write source files, configuration, and dependencies into the isolated workspace directory.",
    },
    "execute_tests": {
        "title": "Run Automated Tests & Verification",
        "risk_level": "medium",
        "description": "Execute unit and integration tests inside isolated execution sandbox.",
    },
    "create_github_repo": {
        "title": "Create Remote GitHub Repository",
        "risk_level": "high",
        "description": "Create a new private or public repository under your GitHub account.",
    },
    "push_github_code": {
        "title": "Push Code to GitHub",
        "risk_level": "high",
        "description": "Commit verified project files and push to remote GitHub repository.",
    },
    "deploy_cloud": {
        "title": "Deploy Project to Cloud Provider",
        "risk_level": "high",
        "description": "Deploy software to live cloud provider (Vercel, Render) with public URL.",
    },
    "delete_project": {
        "title": "Delete Project Workspace",
        "risk_level": "critical",
        "description": "Permanently remove project and all associated files from disk.",
    },
}


class ApprovalEngine:
    """
    Manages workflow state transitions, approval creation, parameter binding,
    and backend permission checks with replay prevention.
    """

    @staticmethod
    async def request_approval(
        db: AsyncSession,
        user_id: str,
        action_type: str,
        project_id: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        proposed_action: Optional[Dict[str, Any]] = None,
        action_params: Optional[Dict[str, Any]] = None,
        expected_result: Optional[str] = None,
        risks: Optional[str] = None,
        costs: Optional[str] = None,
        expires_hours: int = 24,
    ) -> Approval:
        """
        Create a pending approval request bound to exact execution parameters.
        """
        config = PROTECTED_ACTIONS.get(action_type, {
            "title": f"Approve Action: {action_type}",
            "risk_level": "medium",
            "description": "Action requires user authorization.",
        })

        params = action_params or (proposed_action.get("params") if proposed_action else {}) or {}
        params_hash = compute_params_hash(params)

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=expires_hours)

        approval = Approval(
            owner_id=user_id,
            project_id=project_id,
            action_type=action_type,
            title=title or config["title"],
            description=description or config["description"],
            risk_level=config["risk_level"],
            proposed_action=proposed_action or {},
            action_params=params,
            action_params_hash=params_hash,
            expected_result=expected_result or "Proceed with next workflow stage.",
            risks=risks or "None identified for sandbox operations.",
            costs=costs or "Free / within free tier limits.",
            decision="pending",
            consumed=False,
            created_at=now,
            expires_at=expires_at,
        )
        db.add(approval)

        log = AuditLog(
            user_id=user_id,
            project_id=project_id,
            action=f"approval_requested_{action_type}",
            category="approval",
            description=f"Approval requested: {approval.title}",
            details={"action_type": action_type, "params_hash": params_hash},
        )
        db.add(log)
        await db.commit()
        await db.refresh(approval)
        return approval

    @staticmethod
    async def verify_approved(
        db: AsyncSession,
        user_id: str,
        action_type: str,
        project_id: Optional[str] = None,
        action_params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Approval]:
        """
        Strictly verify that an action has an approved, unexpired, and unconsumed approval record
        matching the exact owner, project, and bound action parameters.
        """
        query = select(Approval).where(
            Approval.owner_id == user_id,
            Approval.action_type == action_type,
            Approval.decision == "approved",
            Approval.consumed.is_(False),
        )
        if project_id:
            query = query.where(Approval.project_id == project_id)

        query = query.order_by(Approval.decided_at.desc())
        result = await db.execute(query)
        approvals = result.scalars().all()

        now = datetime.now(timezone.utc)
        for app in approvals:
            # Check expiry
            exp = app.expires_at if (app.expires_at and app.expires_at.tzinfo) else (app.expires_at.replace(tzinfo=timezone.utc) if app.expires_at else None)
            if exp and now > exp:
                app.decision = "expired"
                await db.commit()
                continue

            # Check action params binding
            if action_params is not None and app.action_params_hash:
                current_hash = compute_params_hash(action_params)
                if current_hash != app.action_params_hash:
                    logger.warning(f"Approval {app.id} parameter hash mismatch: expected {app.action_params_hash}, got {current_hash}")
                    continue

            return app

        return None

    @staticmethod
    async def consume_approval(
        db: AsyncSession,
        user_id: str,
        action_type: str,
        project_id: Optional[str] = None,
        action_params: Optional[Dict[str, Any]] = None,
    ) -> Approval:
        """
        Consume an approved permission record atomically to prevent replay attacks.
        Raises PermissionError if no valid unconsumed approval is found.
        """
        approval = await ApprovalEngine.verify_approved(
            db=db,
            user_id=user_id,
            action_type=action_type,
            project_id=project_id,
            action_params=action_params,
        )
        if not approval:
            raise PermissionError(
                f"Action '{action_type}' requires an active, unconsumed user approval. "
                f"No valid approved record found for user {user_id} and project {project_id}."
            )

        now = datetime.now(timezone.utc)
        from sqlalchemy import update
        stmt = (
            update(Approval)
            .where(
                Approval.id == approval.id,
                Approval.consumed.is_(False),
                Approval.decision == "approved",
            )
            .values(consumed=True, consumed_at=now)
        )
        update_res = await db.execute(stmt)
        if update_res.rowcount == 0:
            raise PermissionError(
                f"Approval {approval.id} has already been consumed or modified concurrently."
            )

        log = AuditLog(
            user_id=user_id,
            project_id=project_id,
            action=f"approval_consumed_{action_type}",
            category="approval",
            description=f"Consumed approval {approval.id} for {action_type}",
            details={"approval_id": approval.id, "action_type": action_type},
        )
        db.add(log)
        await db.commit()
        await db.refresh(approval)
        return approval

    @staticmethod
    async def reject_approval(
        db: AsyncSession,
        user_id: str,
        approval_id: str,
        reason: Optional[str] = None,
    ) -> Approval:
        """Explicitly reject a pending approval request."""
        res = await db.execute(
            select(Approval).where(Approval.id == approval_id, Approval.owner_id == user_id)
        )
        approval = res.scalar_one_or_none()
        if not approval:
            raise ValueError("Approval not found")

        now = datetime.now(timezone.utc)
        approval.decision = "rejected"
        approval.decision_reason = reason or "Rejected by user"
        approval.decided_at = now

        log = AuditLog(
            user_id=user_id,
            project_id=approval.project_id,
            action="approval_rejected",
            category="approval",
            description=f"Rejected: {approval.title}",
            details={"approval_id": approval.id, "reason": approval.decision_reason},
        )
        db.add(log)
        await db.commit()
        await db.refresh(approval)
        return approval

    @staticmethod
    async def expire_pending_approvals(db: AsyncSession) -> int:
        """Expire all pending approvals that have exceeded their validity duration."""
        now = datetime.now(timezone.utc)
        res = await db.execute(
            select(Approval).where(
                Approval.decision == "pending",
                Approval.expires_at <= now,
            )
        )
        expired_items = res.scalars().all()
        for item in expired_items:
            item.decision = "expired"

        if expired_items:
            await db.commit()
        return len(expired_items)

    @staticmethod
    async def get_or_create_workflow(
        db: AsyncSession,
        entity_id: str,
        user_id: str,
        entity_type: str = "project",
        mode: str = "hybrid",
    ) -> WorkflowState:
        """Get or initialize a workflow state machine record."""
        result = await db.execute(
            select(WorkflowState).where(
                WorkflowState.entity_type == entity_type,
                WorkflowState.entity_id == entity_id,
                WorkflowState.owner_id == user_id,
            )
        )
        wf = result.scalar_one_or_none()
        if not wf:
            wf = WorkflowState(
                entity_type=entity_type,
                entity_id=entity_id,
                owner_id=user_id,
                state="planning",
                current_step="opportunity_selection",
                operating_mode=mode,
                step_data={"stage": "opportunity_selection", "stages_completed": []},
            )
            db.add(wf)
            await db.commit()
            await db.refresh(wf)
        return wf

