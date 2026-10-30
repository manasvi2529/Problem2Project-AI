"""Approval model — workflow state machine and approval enforcement."""
import uuid
import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy import String, DateTime, Text, JSON, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from backend.database import Base


def compute_params_hash(params: dict) -> str:
    """Compute a deterministic SHA-256 hash of action parameters for integrity binding."""
    serialized = json.dumps(params or {}, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


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
    """Individual approval request for a protected consequential action."""
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=True, index=True)

    # What action requires approval
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # e.g.: select_opportunity, approve_architecture, generate_workspace,
    #       execute_tests, create_github_repo, push_github_code, deploy_cloud, delete_project

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")

    # Proposed changes and exact bound execution parameters
    proposed_action: Mapped[dict] = mapped_column(JSON, default=dict)
    action_params: Mapped[dict] = mapped_column(JSON, default=dict)
    action_params_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    expected_result: Mapped[str] = mapped_column(Text, default="")
    risks: Mapped[str] = mapped_column(Text, default="")
    costs: Mapped[str] = mapped_column(Text, default="")

    # Decision / Status: pending | approved | rejected | modified | expired | cancelled
    decision: Mapped[str] = mapped_column(String(20), default="pending")
    decision_reason: Mapped[str] = mapped_column(Text, default="")
    modifications: Mapped[dict] = mapped_column(JSON, default=dict)

    # Single-use consumption tracking to prevent replay attacks
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Timestamps & Expiry (default: 24h validity window)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc) + timedelta(hours=24)
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Category for risk-based boundaries
    risk_level: Mapped[str] = mapped_column(String(20), default="medium")  # low | medium | high | critical

    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        # Normalize timezone awareness
        exp = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > exp

    def to_dict(self):
        effective_decision = "expired" if (self.decision == "pending" and self.is_expired) else self.decision
        return {
            "id": self.id,
            "project_id": self.project_id,
            "action_type": self.action_type,
            "title": self.title,
            "description": self.description,
            "proposed_action": self.proposed_action or {},
            "action_params": self.action_params or {},
            "expected_result": self.expected_result,
            "risks": self.risks,
            "costs": self.costs,
            "decision": effective_decision,
            "status": effective_decision,
            "decision_reason": self.decision_reason,
            "consumed": bool(self.consumed),
            "consumed_at": self.consumed_at.isoformat() if self.consumed_at else None,
            "risk_level": self.risk_level,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
            "is_expired": self.is_expired,
        }
