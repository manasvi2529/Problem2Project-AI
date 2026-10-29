"""Audit log model — tracks all significant actions for transparency."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from backend.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=True, index=True)

    # Action tracking
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="general")
    # auth | research | project | approval | execution | github | deployment | settings

    description: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)

    # Result
    status: Mapped[str] = mapped_column(String(20), default="success")  # success | failure | error
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    # IP and context
    ip_address: Mapped[str] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[str] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "action": self.action,
            "category": self.category,
            "description": self.description,
            "status": self.status,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
