"""
ProblemPilot AI — Permission & Approval Engine
State machine governing protected operations and enforcing operating mode boundaries
(Autonomous, Guided, Hybrid) with persistent audit logs.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.models.approval import Approval, WorkflowState
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
    Manages workflow state transitions, approval creation, and backend permission checks.
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
        expected_result: Optional[str] = None,
        risks: Optional[str] = None,
        costs: Optional[str] = None,
    ) -> Approval:
        """
        Create a pending approval request for a protected action.
        """
        config = PROTECTED_ACTIONS.get(action_type, {
            "title": f"Approve Action: {action_type}",
            "risk_level": "medium",
            "description": "Action requires user authorization.",
        })

        approval = Approval(
            owner_id=user_id,
            project_id=project_id,
            action_type=action_type,
            title=title or config["title"],
            description=description or config["description"],
            risk_level=config["risk_level"],
            proposed_action=proposed_action or {},
            expected_result=expected_result or "Proceed with next workflow stage.",
            risks=risks or "None identified for sandbox operations.",
            costs=costs or "Free / within free tier limits.",
            decision="pending",
        )
        db.add(approval)

        log = AuditLog(
            user_id=user_id,
            project_id=project_id,
            action=f"approval_requested_{action_type}",
            category="approval",
            description=f"Approval requested: {approval.title}",
            details={"action_type": action_type},
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
    ) -> bool:
        """
        Strictly verify that an action has been explicitly approved by the user.
        """
        query = select(Approval).where(
            Approval.owner_id == user_id,
            Approval.action_type == action_type,
            Approval.decision == "approved",
        )
        if project_id:
            query = query.where(Approval.project_id == project_id)

        query = query.order_by(Approval.decided_at.desc())
        result = await db.execute(query)
        latest_approval = result.scalars().first()
        return bool(latest_approval)

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

