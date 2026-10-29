"""
Projects router — create, manage, and generate projects from problems.
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
from backend.models.project import Project, ProjectFile
from backend.models.research import ProblemCandidate
from backend.models.approval import Approval, WorkflowState
from backend.models.audit import AuditLog
from backend.services.research_service import analyze_with_ai
from backend.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/projects", tags=["projects"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    problem_id: str = ""
    description: str = ""

class UpdateProjectRequest(BaseModel):
    name: str = None
    description: str = None
    status: str = None
    blueprint: dict = None
    tech_stack: dict = None
    tasks: list = None

class GenerateBlueprintRequest(BaseModel):
    problem_id: str


# ── Background Blueprint Generation ─────────────────────────────────────────

async def generate_blueprint_task(project_id: str, problem_title: str, problem_desc: str):
    """Generate project blueprint using AI."""
    from backend.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            return

        prompt = f"""You are a senior software architect. Create a detailed project blueprint for solving this problem:

Problem: {problem_title}
Description: {problem_desc}

Generate a JSON object with these sections:
{{
  "problem_statement": "Clear problem statement",
  "target_users": "Who will use this",
  "evidence_supporting_need": "Why this matters",
  "proposed_solution": "What to build",
  "core_features": ["feature1", "feature2", ...],
  "non_goals": ["what NOT to build"],
  "user_journeys": [
    {{"name": "journey name", "steps": ["step1", "step2"]}}
  ],
  "requirements": {{
    "functional": ["req1", "req2"],
    "non_functional": ["perf req", "security req"]
  }},
  "architecture": {{
    "overview": "Architecture description",
    "frontend": "Frontend tech and approach",
    "backend": "Backend tech and approach",
    "database": "Database design overview",
    "api_design": "API approach"
  }},
  "tech_stack": {{
    "frontend": ["tech1"],
    "backend": ["tech1"],
    "database": "db choice",
    "deployment": "deploy target"
  }},
  "database_schema": [
    {{"table": "name", "columns": ["col1 TYPE", "col2 TYPE"], "purpose": "why"}}
  ],
  "api_endpoints": [
    {{"method": "GET", "path": "/api/...", "purpose": "what it does"}}
  ],
  "testing_strategy": {{
    "unit_tests": "approach",
    "integration_tests": "approach",
    "e2e_tests": "approach"
  }},
  "milestones": [
    {{"name": "MVP", "tasks": ["task1", "task2"], "estimated_days": 5}}
  ],
  "privacy_security": ["consideration1", "consideration2"],
  "success_metrics": ["metric1", "metric2"],
  "estimated_effort": "X weeks for MVP"
}}

Return ONLY valid JSON. No markdown wrapping."""

        try:
            ai_response = await analyze_with_ai(prompt)
            if ai_response:
                cleaned = ai_response.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("\n", 1)[1]
                    cleaned = cleaned.rsplit("```", 1)[0].strip()
                blueprint = json.loads(cleaned)
                project.blueprint = blueprint
                project.tech_stack = blueprint.get("tech_stack", {})
                project.status = "planning"

                # Generate task checklist from milestones
                tasks = []
                for ms in blueprint.get("milestones", []):
                    for task in ms.get("tasks", []):
                        tasks.append({
                            "id": f"task-{len(tasks)+1}",
                            "title": task,
                            "milestone": ms.get("name", ""),
                            "status": "pending",
                        })
                project.tasks = tasks
            else:
                project.status = "draft"
                project.blueprint = {"error": "AI provider not configured or failed"}
        except Exception as e:
            logger.error(f"Blueprint generation failed: {e}")
            project.blueprint = {"error": str(e)}
            project.status = "draft"

        await db.commit()


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("")
async def create_project(
    body: CreateProjectRequest,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    project = Project(
        owner_id=user.id,
        name=body.name,
        description=body.description,
        problem_id=body.problem_id or None,
    )
    db.add(project)

    # Create workflow state
    wf = WorkflowState(
        entity_type="project", entity_id=project.id,
        owner_id=user.id, state="draft", current_step="created",
        operating_mode=user.operating_mode,
    )
    db.add(wf)

    log = AuditLog(
        user_id=user.id, action="create_project", category="project",
        description=f"Project created: {body.name}", details={"project_id": project.id},
    )
    db.add(log)

    await db.commit()
    await db.refresh(project)
    return {"project": project.to_dict()}


@router.get("")
async def list_projects(
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project)
        .where(Project.owner_id == user.id)
        .order_by(Project.updated_at.desc())
    )
    projects = result.scalars().all()
    return {"projects": [p.to_dict() for p in projects]}


@router.get("/{project_id}")
async def get_project(
    project_id: str,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id, Project.owner_id == user.id)
        .options(selectinload(Project.files))
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return {
        "project": project.to_dict(),
        "files": [f.to_dict() for f in project.files],
    }


@router.put("/{project_id}")
async def update_project(
    project_id: str,
    body: UpdateProjectRequest,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    if body.status is not None:
        project.status = body.status
    if body.blueprint is not None:
        project.blueprint = body.blueprint
    if body.tech_stack is not None:
        project.tech_stack = body.tech_stack
    if body.tasks is not None:
        project.tasks = body.tasks

    project.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(project)
    return {"project": project.to_dict()}


@router.post("/{project_id}/generate-blueprint")
async def generate_blueprint(
    project_id: str,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Generate a project blueprint from the linked problem using AI."""
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not settings.ai_configured:
        raise HTTPException(status_code=503, detail="AI provider not configured")

    # Get problem info
    problem_title = project.name
    problem_desc = project.description
    if project.problem_id:
        prob_result = await db.execute(
            select(ProblemCandidate).where(ProblemCandidate.id == project.problem_id)
        )
        problem = prob_result.scalar_one_or_none()
        if problem:
            problem_title = problem.title
            problem_desc = problem.description

    project.status = "planning"
    await db.commit()

    background_tasks.add_task(generate_blueprint_task, project_id, problem_title, problem_desc)

    return {
        "message": "Blueprint generation started",
        "project_id": project_id,
    }


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Delete a project — requires it to be the owner."""
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check for pending approval
    approval_result = await db.execute(
        select(Approval).where(
            Approval.project_id == project_id,
            Approval.action_type == "delete_project",
            Approval.decision == "approved",
        )
    )
    approval = approval_result.scalar_one_or_none()
    if not approval:
        # Create approval request
        appr = Approval(
            owner_id=user.id, project_id=project_id,
            action_type="delete_project",
            title=f"Delete project: {project.name}",
            description="This will permanently delete the project and all its files.",
            risks="Permanent data loss. This action cannot be undone.",
            risk_level="critical",
        )
        db.add(appr)
        await db.commit()
        await db.refresh(appr)
        return {
            "message": "Approval required to delete project",
            "approval": appr.to_dict(),
        }

    # Approved — proceed with deletion
    log = AuditLog(
        user_id=user.id, action="delete_project", category="project",
        description=f"Project deleted: {project.name}",
    )
    db.add(log)
    await db.delete(project)
    await db.commit()
    return {"message": "Project deleted"}
