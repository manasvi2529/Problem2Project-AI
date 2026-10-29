"""Approval model — workflow state machine and approval enforcement."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from backend.database import Base


class WorkflowState(Base):
    """Tracks the state of any workflow (research, project, deployment, etc.)."""
    __tablename__ = "workflow_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # project | research | deployment
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    # State: draft | researching | awaiting_approval | approved | rejected |
    #        in_progress | paused | failed | completed | cancelled
    state: Mapped[str] = mapped_column(String(30), default="draft")
    previous_state: Mapped[str] = mapped_column(String(30), nullable=True)

    # Current step in the workflow
    current_step: Mapped[str] = mapped_column(String(100), default="")
    step_data: Mapped[dict] = mapped_column(JSON, default=dict)

    # Mode tracking
    operating_mode: Mapped[str] = mapped_column(String(20), default="hybrid")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "state": self.state,
            "previous_state": self.previous_state,
            "current_step": self.current_step,
            "operating_mode": self.operating_mode,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Approval(Base):
    """Individual approval request for a protected action."""
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=True, index=True)

    # What action requires approval
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # e.g.: select_problem, approve_architecture, install_dependency,
    #       create_repo, push_code, deploy_public, delete_project, etc.

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")

    # Proposed changes / details
    proposed_action: Mapped[dict] = mapped_column(JSON, default=dict)
    expected_result: Mapped[str] = mapped_column(Text, default="")
    risks: Mapped[str] = mapped_column(Text, default="")
    costs: Mapped[str] = mapped_column(Text, default="")

    # Decision: pending | approved | rejected | modified | expired
    decision: Mapped[str] = mapped_column(String(20), default="pending")
    decision_reason: Mapped[str] = mapped_column(Text, default="")
    modifications: Mapped[dict] = mapped_column(JSON, default=dict)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    decided_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # Category for risk-based boundaries
    risk_level: Mapped[str] = mapped_column(String(20), default="medium")  # low | medium | high | critical

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "action_type": self.action_type,
            "title": self.title,
            "description": self.description,
            "proposed_action": self.proposed_action or {},
            "expected_result": self.expected_result,
            "risks": self.risks,
            "costs": self.costs,
            "decision": self.decision,
            "decision_reason": self.decision_reason,
            "risk_level": self.risk_level,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
        }
