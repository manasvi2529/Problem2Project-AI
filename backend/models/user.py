"""User model — authentication, profile, and settings."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Operating mode preference: autonomous | guided | hybrid
    operating_mode: Mapped[str] = mapped_column(String(20), default="hybrid")

    # Settings stored as JSON
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)

    # GitHub integration
    github_access_token: Mapped[str] = mapped_column(Text, nullable=True)
    github_username: Mapped[str] = mapped_column(String(100), nullable=True)
    github_connected_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # Relationships
    projects = relationship("Project", back_populates="owner", cascade="all, delete-orphan")
    research_sessions = relationship("ResearchSession", back_populates="owner", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "username": self.username,
            "full_name": self.full_name,
            "operating_mode": self.operating_mode,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "github_connected": bool(self.github_access_token),
            "github_username": self.github_username,
            "preferences": self.preferences or {},
        }
