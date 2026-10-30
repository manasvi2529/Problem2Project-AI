"""
Deployment model — tracks cloud deployment history, provider deployment IDs, and verification logs.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.database import Base


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    provider: Mapped[str] = mapped_column(String(50), default="vercel")  # vercel | render | docker
    deployment_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    deploy_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Status: queued | building | ready | verified | failed
    status: Mapped[str] = mapped_column(String(30), default="queued")
    error_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manifests_generated: Mapped[list] = mapped_column(JSON, default=list)
    health_check_result: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "owner_id": self.owner_id,
            "provider": self.provider,
            "deployment_id": self.deployment_id,
            "deploy_url": self.deploy_url,
            "status": self.status,
            "error_details": self.error_details,
            "manifests_generated": self.manifests_generated or [],
            "health_check_result": self.health_check_result or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
        }

