"""Research models — sessions, sources, and evidence."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, JSON, ForeignKey, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.database import Base


class ResearchSession(Base):
    __tablename__ = "research_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(200), default="")
    target_users: Mapped[str] = mapped_column(Text, default="")
    geography: Mapped[str] = mapped_column(String(200), default="")
    constraints: Mapped[str] = mapped_column(Text, default="")

    # Status: pending | searching | analyzing | completed | failed
    status: Mapped[str] = mapped_column(String(30), default="pending")
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    # Whether live search was used or fallback
    used_live_search: Mapped[bool] = mapped_column(default=False)
    search_provider: Mapped[str] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # Relationships
    owner = relationship("User", back_populates="research_sessions")
    sources = relationship("ResearchSource", back_populates="session", cascade="all, delete-orphan")
    problems = relationship("ProblemCandidate", back_populates="session", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "query": self.query,
            "domain": self.domain,
            "target_users": self.target_users,
            "geography": self.geography,
            "status": self.status,
            "used_live_search": self.used_live_search,
            "search_provider": self.search_provider,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "source_count": len(self.sources) if self.sources else 0,
            "problem_count": len(self.problems) if self.problems else 0,
        }


class ResearchSource(Base):
    __tablename__ = "research_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_sessions.id"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, default="")
    publisher: Mapped[str] = mapped_column(String(300), default="")
    snippet: Mapped[str] = mapped_column(Text, default="")
    full_text: Mapped[str] = mapped_column(Text, default="")
    publication_date: Mapped[str] = mapped_column(String(50), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    reliability: Mapped[str] = mapped_column(String(30), default="unassessed")  # high | medium | low | unassessed
    source_type: Mapped[str] = mapped_column(String(50), default="web")  # web | report | dataset | discussion | news
    limitations: Mapped[str] = mapped_column(Text, default="")
    key_findings: Mapped[str] = mapped_column(Text, default="")

    session = relationship("ResearchSession", back_populates="sources")

    def to_dict(self):
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "publisher": self.publisher,
            "snippet": self.snippet,
            "publication_date": self.publication_date,
            "retrieved_at": self.retrieved_at.isoformat() if self.retrieved_at else None,
            "relevance_score": self.relevance_score,
            "reliability": self.reliability,
            "source_type": self.source_type,
            "key_findings": self.key_findings,
            "limitations": self.limitations,
        }


class ProblemCandidate(Base):
    __tablename__ = "problem_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_sessions.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    affected_users: Mapped[str] = mapped_column(Text, default="")
    existing_solutions: Mapped[str] = mapped_column(Text, default="")
    solution_gaps: Mapped[str] = mapped_column(Text, default="")
    evidence_summary: Mapped[str] = mapped_column(Text, default="")

    # Transparent scoring — each dimension 0-10 with explanations
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    # Structure: {"severity": {"score": 7, "explanation": "...", "confidence": "medium"},  ...}
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    score_weights: Mapped[dict] = mapped_column(JSON, default=dict)

    # Evidence tracking
    source_ids: Mapped[list] = mapped_column(JSON, default=list)  # IDs of supporting sources
    evidence_gaps: Mapped[list] = mapped_column(JSON, default=list)
    contradictions: Mapped[list] = mapped_column(JSON, default=list)

    # Claim types
    claim_type: Mapped[str] = mapped_column(String(30), default="inference")
    # verified_fact | source_backed | inference | hypothesis

    # Status: identified | evaluated | selected | rejected
    status: Mapped[str] = mapped_column(String(20), default="identified")
    rank: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    session = relationship("ResearchSession", back_populates="problems")
    project = relationship("Project", back_populates="problem", uselist=False)

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "title": self.title,
            "description": self.description,
            "affected_users": self.affected_users,
            "existing_solutions": self.existing_solutions,
            "solution_gaps": self.solution_gaps,
            "evidence_summary": self.evidence_summary,
            "scores": self.scores or {},
            "overall_score": self.overall_score,
            "evidence_gaps": self.evidence_gaps or [],
            "contradictions": self.contradictions or [],
            "claim_type": self.claim_type,
            "status": self.status,
            "rank": self.rank,
            "source_ids": self.source_ids or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
