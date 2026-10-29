"""
Platform research router — dedicated endpoints for scraping real-world
problems from Reddit, HackerNews, StackOverflow, GitHub, Dev.to,
combined with Data Science analytics (Pandas, Scikit-learn) and AI synthesis.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field

from backend.database import get_db
from backend.routers.auth import get_user_from_token
from backend.models.user import User
from backend.models.research import ResearchSession, ResearchSource, ProblemCandidate
from backend.models.audit import AuditLog
from backend.services.platform_scrapers import (
    scrape_all_platforms, scrape_reddit, scrape_hackernews,
    scrape_stackoverflow, scrape_github_trending, scrape_devto,
)
from backend.services.research_service import analyze_with_ai, build_scoring_weights
from backend.services.ds_problem_analyzer import DataScienceProblemAnalyzer
from backend.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/discover", tags=["discover"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class DiscoverRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=300)
    platforms: list[str] = ["reddit", "hackernews", "stackoverflow", "devto"]
    subreddits: list[str] = []
    domain: str = ""
    geography: str = ""

class QuickSearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=300)
    platform: str = "reddit"


# ── Background Discovery Pipeline ───────────────────────────────────────────

async def run_discovery_pipeline(session_id: str, query: str, platforms: list, subreddits: list):
    """Full pipeline: scrape platforms → Data Science analysis (Pandas/Scikit-learn) → AI synthesis."""
    from backend.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ResearchSession).where(ResearchSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            return

        try:
            # Step 1: Scrape all platforms
            session.status = "searching"
            await db.commit()

            scraped = await scrape_all_platforms(query, platforms, subreddits)

            # Step 2: Save sources into database permanently for data retention
            session.status = "analyzing"
            session.used_live_search = True
            session.search_provider = ",".join(scraped["platforms_queried"])
            await db.commit()

            all_items = []
            for platform, items in scraped["results"].items():
                for item in items:
                    source = ResearchSource(
                        session_id=session_id,
                        url=item.get("url", ""),
                        title=item.get("title", ""),
                        publisher=f"{platform} — {item.get('author', 'unknown')}",
                        snippet=item.get("content", "")[:500],
                        full_text=item.get("content", ""),
                        source_type=platform,
                        reliability="high" if item.get("score", 0) > 10 else "medium",
                        relevance_score=float(item.get("score", 0)),
                        key_findings=json.dumps({
                            "platform": platform,
                            "score": item.get("score", 0),
                            "comments": item.get("num_comments", item.get("comments_count", 0)),
                            "subreddit": item.get("subreddit", ""),
                            "tags": item.get("tags", []),
                        }),
                    )
                    db.add(source)
                    all_items.append(item)

            await db.commit()

            # Step 3: Data Science Engine (Pandas DataFrame, Scikit-learn TF-IDF Clustering & Pain Scoring)
            ds_analyzer = DataScienceProblemAnalyzer(all_items)
            ds_analyzer.compute_metrics()
            ds_analyzer.cluster_topics(n_clusters=4)
            ds_opportunities = ds_analyzer.get_top_opportunities(top_n=8)

            src_result = await db.execute(
                select(ResearchSource.id).where(ResearchSource.session_id == session_id)
            )
            source_ids = [r[0] for r in src_result.all()]
            weights = build_scoring_weights()

            # Step 4: AI Analysis if configured; otherwise use Data Science metrics directly
            if settings.ai_configured and all_items:
                content_summary = ""
                for i, item in enumerate(all_items[:25], 1):
                    platform = item.get("platform", "unknown")
                    content_summary += f"\n[{i}] [{platform}] {item.get('title', '')}\n"
                    content_summary += f"    Score: {item.get('score', 0)} | Comments: {item.get('num_comments', 0)}\n"
                    if item.get("subreddit"):
                        content_summary += f"    Subreddit: r/{item['subreddit']}\n"
                    content = item.get("content", "")[:300]
                    if content:
                        content_summary += f"    Snippet: {content}\n"

                prompt = f"""You are analyzing real discussions from Reddit, HackerNews, StackOverflow, and developer communities.
Research Query: "{query}"

Here are real user discussions scraped:
{content_summary}

Based on these discussions, identify 3-6 distinct real-world problems.
Return ONLY a valid JSON array of objects with:
- "title": Clear problem statement
- "description": Why it matters and context
- "affected_users": Who suffers from this
- "existing_solutions": Current tools/workarounds
- "solution_gaps": What is missing
- "evidence_summary": Citing actual posts/platforms
- "claim_type": "source_backed"
- "scores": Object with dimensions (severity, scale, evidence_strength, urgency, feasibility, differentiation, effort: 0-10 each with "score" and "explanation")
- "evidence_gaps": Array of unknowns
- "contradictions": Conflicting opinions
- "project_idea": Software concept to solve this
"""
                ai_response = await analyze_with_ai(prompt)
                if ai_response:
                    try:
                        cleaned = ai_response.strip()
                        if cleaned.startswith("```"):
                            cleaned = cleaned.split("\n", 1)[1]
                            cleaned = cleaned.rsplit("```", 1)[0].strip()
                        problems = json.loads(cleaned)

                        for i, p in enumerate(problems):
                            scores = p.get("scores", {})
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
                                claim_type=p.get("claim_type", "source_backed"),
                                scores=scores,
                                overall_score=round(overall, 2),
                                score_weights=weights,
                                evidence_gaps=p.get("evidence_gaps", []),
                                contradictions=p.get("contradictions", []),
                                source_ids=source_ids[:20],
                                rank=i + 1,
                                status="evaluated",
                            )
                            db.add(problem)
                    except Exception as e:
                        logger.error(f"AI response JSON parse error: {e}. Falling back to Data Science extraction.")
                        self._populate_candidates_from_ds(db, session_id, ds_opportunities, source_ids, weights)
                else:
                    self._populate_candidates_from_ds(db, session_id, ds_opportunities, source_ids, weights)
            else:
                # Direct Data Science pipeline (deterministic NLP + Pandas)
                for i, opp in enumerate(ds_opportunities):
                    p_metric = opp["metrics"]
                    p_potential = opp["project_potential"]

                    scores = {
                        "severity": {"score": min(10.0, p_metric["pain_intensity"]), "explanation": "Calculated via lexical frustration density"},
                        "scale": {"score": min(10.0, p_metric["engagement_score"]), "explanation": f"Grounded in {p_metric['raw_upvotes']} upvotes and {p_metric['raw_comments']} comments"},
                        "evidence_strength": {"score": 8.5, "explanation": f"Directly observed on {opp['platform']}"},
                        "urgency": {"score": min(10.0, p_metric["urgency_score"]), "explanation": "Urgency keyword frequency in community discussion"},
                        "feasibility": {"score": round(p_potential["feasibility_score"] / 10.0, 1), "explanation": f"Assessed as {p_potential['difficulty']} implementation"},
                        "differentiation": {"score": 7.5, "explanation": "Observed gap in current tooling"},
                        "effort": {"score": 7.0 if p_potential["difficulty"] == "Easy" else 5.0, "explanation": "Estimated engineering complexity"},
                    }

                    overall = sum(scores[dim]["score"] * weights.get(dim, 1.0) for dim in scores) / sum(weights.values())

                    problem = ProblemCandidate(
                        session_id=session_id,
                        title=opp["title"],
                        description=f"{opp['problem_statement']}\n\nSuggested Solution: {p_potential['suggested_solution']}",
                        affected_users=p_potential["target_audience"],
                        existing_solutions="Manual workarounds, spreadsheets, or legacy fragmented tools",
                        solution_gaps="Lacks automation, modern UX, or specialized workflows",
                        evidence_summary=f"Discovered on {opp['platform']} ({opp.get('subreddit') or 'general'}). Source URL: {opp['source_url']}",
                        claim_type="source_backed",
                        scores=scores,
                        overall_score=round(overall, 2),
                        score_weights=weights,
                        evidence_gaps=["User interviews recommended to confirm pricing tolerance"],
                        contradictions=[],
                        source_ids=source_ids[:20],
                        rank=i + 1,
                        status="evaluated",
                    )
                    db.add(problem)

            session.status = "completed"
            session.completed_at = datetime.now(timezone.utc)
            if scraped["errors"]:
                session.error_message = "; ".join(scraped["errors"])
            await db.commit()

        except Exception as e:
            logger.error(f"Discovery pipeline failed: {e}", exc_info=True)
            session.status = "failed"
            session.error_message = str(e)
            await db.commit()


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/search")
async def discover_problems(
    body: DiscoverRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """
    Start a discovery session: scrapes Reddit, HackerNews, StackOverflow, Dev.to
    for real-world problems, runs Data Science analytics (Pandas/Scikit-learn),
    and retains all data for software project creation.
    """
    session = ResearchSession(
        owner_id=user.id,
        query=body.query,
        domain=body.domain,
        geography=body.geography,
        status="pending",
    )
    db.add(session)

    log = AuditLog(
        user_id=user.id, action="start_discovery", category="research",
        description=f"Discovery started: {body.query} on {', '.join(body.platforms)}",
    )
    db.add(log)
    await db.commit()
    await db.refresh(session)

    background_tasks.add_task(
        run_discovery_pipeline, session.id, body.query, body.platforms, body.subreddits
    )

    return {
        "session": session.to_dict(),
        "message": "Discovery running — scraping platforms & analyzing data science metrics...",
        "platforms": body.platforms,
        "ai_configured": settings.ai_configured,
    }


@router.get("/analytics/{session_id}")
async def get_session_analytics(
    session_id: str,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """
    Get Data Science quantitative metrics (Pandas DataFrame summary,
    pain scores, urgency scores, platform breakdown, and cluster categories).
    """
    result = await db.execute(
        select(ResearchSource).where(ResearchSource.session_id == session_id)
    )
    sources = result.scalars().all()
    if not sources:
        raise HTTPException(status_code=404, detail="No research sources found for this session")

    items = []
    for s in sources:
        extra = {}
        if s.key_findings:
            try:
                extra = json.loads(s.key_findings)
            except Exception:
                pass
        items.append({
            "platform": s.source_type,
            "title": s.title,
            "content": s.full_text or s.snippet,
            "url": s.url,
            "author": s.publisher,
            "score": s.relevance_score,
            "num_comments": extra.get("comments", 0),
            "subreddit": extra.get("subreddit", ""),
        })

    analyzer = DataScienceProblemAnalyzer(items)
    stats = analyzer.get_summary_statistics()
    top_opps = analyzer.get_top_opportunities(top_n=5)

    return {
        "session_id": session_id,
        "statistics": stats,
        "top_data_science_opportunities": top_opps,
    }


@router.get("/export/csv/{session_id}")
async def export_session_csv(
    session_id: str,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Export retained research items to CSV for data scientists."""
    result = await db.execute(
        select(ResearchSource).where(ResearchSource.session_id == session_id)
    )
    sources = result.scalars().all()
    items = []
    for s in sources:
        items.append({
            "platform": s.source_type,
            "title": s.title,
            "content": s.snippet,
            "url": s.url,
            "author": s.publisher,
            "score": s.relevance_score,
        })
    analyzer = DataScienceProblemAnalyzer(items)
    analyzer.compute_metrics()
    csv_data = analyzer.export_csv()

    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=problems_{session_id}.csv"},
    )


@router.get("/quick/{platform}")
async def quick_platform_search(
    platform: str,
    q: str,
    user: User = Depends(get_user_from_token),
):
    """Quick search on a single platform — returns raw results immediately."""
    scrapers = {
        "reddit": lambda: scrape_reddit(q),
        "hackernews": lambda: scrape_hackernews(q),
        "stackoverflow": lambda: scrape_stackoverflow(q),
        "github_trending": lambda: scrape_github_trending(),
        "devto": lambda: scrape_devto(q),
    }

    if platform not in scrapers:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}. Available: {list(scrapers.keys())}")

    try:
        results = await scrapers[platform]()
        analyzer = DataScienceProblemAnalyzer(results)
        analyzer.compute_metrics()
        top_opps = analyzer.get_top_opportunities(top_n=5)

        return {
            "platform": platform,
            "query": q,
            "count": len(results),
            "results": results,
            "data_science_ranked_opportunities": top_opps,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scraping {platform} failed: {str(e)}")


@router.get("/platforms")
async def list_platforms():
    """List available platforms for scraping."""
    return {
        "platforms": [
            {
                "id": "reddit",
                "name": "Reddit",
                "description": "Community discussions, complaints, pain points across r/startups, r/webdev, r/datascience",
                "auth_required": False,
                "status": "available",
            },
            {
                "id": "hackernews",
                "name": "Hacker News",
                "description": "Startup ideas, Ask HN questions, Show HN critiques, dev pain points",
                "auth_required": False,
                "status": "available",
            },
            {
                "id": "stackoverflow",
                "name": "Stack Overflow",
                "description": "Unanswered developer problems, recurring bugs, architectural challenges",
                "auth_required": False,
                "status": "available",
            },
            {
                "id": "github_trending",
                "name": "GitHub Trending",
                "description": "Fastest growing developer tools, repos, and missing ecosystems",
                "auth_required": False,
                "status": "available",
            },
            {
                "id": "devto",
                "name": "Dev.to",
                "description": "Developer blog posts, tool feedback, and community discussions",
                "auth_required": False,
                "status": "available",
            },
        ],
    }
