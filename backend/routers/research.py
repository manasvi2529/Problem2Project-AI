"""
Research router — live problem discovery and evidence collection.
"""
import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, Field

from backend.database import get_db
from backend.routers.auth import get_user_from_token
from backend.models.user import User
from backend.models.research import ResearchSession, ResearchSource, ProblemCandidate
from backend.models.audit import AuditLog
from backend.services.research_service import (
    perform_web_search, fetch_page_content, analyze_with_ai,
    build_analysis_prompt, build_scoring_weights,
)
from backend.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/research", tags=["research"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=500)
    domain: str = ""
    target_users: str = ""
    geography: str = ""
    constraints: str = ""

class RefineRequest(BaseModel):
    additional_query: str = Field(..., min_length=3)


# ── Background Research Task ────────────────────────────────────────────────

async def run_research_pipeline(session_id: str, query: str):
    """Execute the full research pipeline in the background."""
    from backend.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        # Get session
        result = await db.execute(
            select(ResearchSession).where(ResearchSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            return

        try:
            # Step 1: Web search
            session.status = "searching"
            await db.commit()

            search_query = query
            if session.domain:
                search_query = f"{query} {session.domain}"
            if session.geography:
                search_query += f" {session.geography}"

            search_results, provider, is_live = await perform_web_search(search_query)
            session.used_live_search = is_live
            session.search_provider = provider

            if not search_results and not is_live:
                session.status = "failed"
                session.error_message = (
                    f"Search provider '{provider}' is not configured or returned no results. "
                    f"Please configure SEARCH_API_KEY in your .env file. "
                    f"Supported providers: google_custom, serper, brave."
                )
                await db.commit()
                return

            # Step 2: Fetch page content for top results
            session.status = "analyzing"
            await db.commit()

            sources_data = []
            for sr in search_results[:8]:  # Limit to 8 pages
                page = await fetch_page_content(sr["url"])
                source = ResearchSource(
                    session_id=session_id,
                    url=sr["url"],
                    title=sr.get("title", page.get("title", "")),
                    publisher=sr.get("publisher", ""),
                    snippet=sr.get("snippet", ""),
                    full_text=page.get("text", "")[:10000],
                    publication_date=page.get("publication_date"),
                    source_type="web",
                    reliability="unassessed",
                )
                db.add(source)
                sources_data.append({
                    "url": sr["url"],
                    "title": sr.get("title", ""),
                    "snippet": sr.get("snippet", ""),
                    "text": page.get("text", "")[:3000],
                })

            await db.commit()

            # Step 3: AI analysis to extract problems
            if settings.ai_configured:
                prompt = build_analysis_prompt(query, sources_data)
                ai_response = await analyze_with_ai(prompt)

                if ai_response:
                    # Parse the JSON response
                    try:
                        # Clean up potential markdown wrapping
                        cleaned = ai_response.strip()
                        if cleaned.startswith("```"):
                            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
                            cleaned = cleaned.rsplit("```", 1)[0] if "```" in cleaned else cleaned
                            cleaned = cleaned.strip()

                        problems = json.loads(cleaned)
                        weights = build_scoring_weights()

                        # Get source IDs
                        src_result = await db.execute(
                            select(ResearchSource.id).where(ResearchSource.session_id == session_id)
                        )
                        source_ids = [r[0] for r in src_result.all()]

                        for i, p in enumerate(problems):
                            scores = p.get("scores", {})
                            # Calculate weighted overall score
                            overall = 0.0
                            total_weight = 0.0
                            for dim, weight in weights.items():
                                if dim in scores and isinstance(scores[dim], dict):
                                    overall += scores[dim].get("score", 0) * weight
                                    total_weight += weight
                            if total_weight > 0:
                                overall = overall / total_weight

                            problem = ProblemCandidate(
                                session_id=session_id,
                                title=p.get("title", f"Problem {i+1}"),
                                description=p.get("description", ""),
                                affected_users=p.get("affected_users", ""),
                                existing_solutions=p.get("existing_solutions", ""),
                                solution_gaps=p.get("solution_gaps", ""),
                                evidence_summary=p.get("evidence_summary", ""),
                                claim_type=p.get("claim_type", "inference"),
                                scores=scores,
                                overall_score=round(overall, 2),
                                score_weights=weights,
                                evidence_gaps=p.get("evidence_gaps", []),
                                contradictions=p.get("contradictions", []),
                                source_ids=source_ids,
                                rank=i + 1,
                                status="evaluated",
                            )
                            db.add(problem)

                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse AI response: {e}")
                        # Create a single problem from raw AI response
                        problem = ProblemCandidate(
                            session_id=session_id,
                            title="AI analysis available (parsing failed)",
                            description=ai_response[:2000],
                            claim_type="inference",
                            status="identified",
                            rank=1,
                        )
                        db.add(problem)
            else:
                # No AI configured — still save sources, note limitation
                session.error_message = (
                    "AI provider not configured. Sources were collected but problem extraction "
                    "requires a configured AI provider (set GOOGLE_API_KEY or ANTHROPIC_API_KEY)."
                )

            session.status = "completed"
            session.completed_at = datetime.now(timezone.utc)
            await db.commit()

        except Exception as e:
            logger.error(f"Research pipeline failed: {e}", exc_info=True)
            session.status = "failed"
            session.error_message = str(e)
            await db.commit()


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/sessions")
async def create_research_session(
    body: ResearchRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Start a new research session with live web search."""
    session = ResearchSession(
        owner_id=user.id,
        query=body.query,
        domain=body.domain,
        target_users=body.target_users,
        geography=body.geography,
        constraints=body.constraints,
        status="pending",
    )
    db.add(session)

    log = AuditLog(
        user_id=user.id, action="start_research", category="research",
        description=f"Research started: {body.query}",
    )
    db.add(log)
    await db.commit()
    await db.refresh(session)

    # Run research pipeline in background
    background_tasks.add_task(run_research_pipeline, session.id, body.query)

    return {
        "session": session.to_dict(),
        "message": "Research session started. Check status with GET /api/research/sessions/{id}",
        "search_configured": settings.search_configured,
        "ai_configured": settings.ai_configured,
    }


@router.get("/sessions")
async def list_research_sessions(
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """List all research sessions for the current user."""
    result = await db.execute(
        select(ResearchSession)
        .where(ResearchSession.owner_id == user.id)
        .order_by(ResearchSession.created_at.desc())
    )
    sessions = result.scalars().all()
    return {"sessions": [s.to_dict() for s in sessions]}


@router.get("/sessions/{session_id}")
async def get_research_session(
    session_id: str,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get a research session with its sources and discovered problems."""
    result = await db.execute(
        select(ResearchSession)
        .where(ResearchSession.id == session_id, ResearchSession.owner_id == user.id)
        .options(selectinload(ResearchSession.sources), selectinload(ResearchSession.problems))
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Research session not found")

    return {
        "session": session.to_dict(),
        "sources": [s.to_dict() for s in session.sources],
        "problems": sorted(
            [p.to_dict() for p in session.problems],
            key=lambda x: x.get("overall_score", 0),
            reverse=True,
        ),
    }


@router.get("/sessions/{session_id}/problems")
async def get_session_problems(
    session_id: str,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get all problem candidates discovered in a specific session."""
    sess_check = await db.execute(
        select(ResearchSession).where(
            ResearchSession.id == session_id,
            ResearchSession.owner_id == user.id,
        )
    )
    if not sess_check.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Research session not found")

    result = await db.execute(
        select(ProblemCandidate)
        .where(ProblemCandidate.session_id == session_id)
        .order_by(ProblemCandidate.overall_score.desc())
    )
    problems = result.scalars().all()
    return {"problems": [p.to_dict() for p in problems]}


@router.get("/integration-status")
async def research_integration_status():
    """Check which research integrations are configured."""
    return {
        "search": {
            "configured": settings.search_configured,
            "provider": settings.SEARCH_PROVIDER,
            "message": (
                "Ready for live search" if settings.search_configured
                else "Not configured. Set SEARCH_API_KEY and SEARCH_ENGINE_ID in .env"
            ),
        },
        "ai": {
            "configured": settings.ai_configured,
            "provider": settings.AI_PROVIDER,
            "message": (
                "AI analysis ready" if settings.ai_configured
                else f"Not configured. Set {'GOOGLE_API_KEY' if settings.AI_PROVIDER == 'google' else 'ANTHROPIC_API_KEY'} in .env"
            ),
        },
    }
