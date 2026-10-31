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
from typing import Optional, List, Dict, Any
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
    name: Optional[str] = None
    title: Optional[str] = None  # Frontend alias
    problem_id: Optional[str] = ""
    problem_candidate_id: Optional[str] = ""  # Frontend alias
    description: Optional[str] = ""
    repository_name: Optional[str] = ""

class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    blueprint: Optional[dict] = None
    tech_stack: Optional[dict] = None
    tasks: Optional[list] = None

class GenerateBlueprintRequest(BaseModel):
    problem_id: Optional[str] = None

class AdvanceWorkflowRequest(BaseModel):
    target_stage: Optional[str] = None


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
    project_name = (body.name or body.title or "Untitled Project").strip()
    if len(project_name) < 2:
        raise HTTPException(status_code=400, detail="Project name must have at least 2 characters")

    problem_id = (body.problem_id or body.problem_candidate_id or "").strip() or None

    import uuid
    project_id = str(uuid.uuid4())
    project = Project(
        id=project_id,
        owner_id=user.id,
        name=project_name,
        description=body.description or "",
        problem_id=problem_id,
        github_repo_name=body.repository_name or "",
        status="planning",
    )
    db.add(project)

    # Create workflow state
    wf = WorkflowState(
        entity_type="project", entity_id=project_id,
        owner_id=user.id, state="planning", current_step="opportunity_selected",
        operating_mode=user.operating_mode,
        step_data={"stage": "opportunity", "stages_completed": ["opportunity"]},
    )
    db.add(wf)

    log = AuditLog(
        user_id=user.id, action="create_project", category="project",
        description=f"Project created: {project_name}", details={"project_id": project.id},
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

    file_list = [f.to_dict() for f in project.files]
    if not file_list:
        from backend.routers.orchestrator import orchestrator
        workspace_dir = orchestrator.workspace_builder.get_workspace_dir(project.id, project.name)
        EXCLUDE_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache"}
        if workspace_dir.exists():
            for p in workspace_dir.rglob("*"):
                if p.is_file():
                    rel = p.relative_to(workspace_dir)
                    parts = set(rel.parts)
                    if parts & EXCLUDE_DIRS or any(part.startswith(".") for part in parts if part != ".gitignore"):
                        continue
                    if p.name.startswith(".env") or p.suffix in (".pyc", ".log", ".pem", ".key"):
                        continue
                    try:
                        content = p.read_text(encoding="utf-8", errors="ignore")
                        ext = p.suffix.lstrip(".")
                        file_list.append({
                            "id": f"disk-{rel.as_posix()}",
                            "project_id": project.id,
                            "path": rel.as_posix(),
                            "name": p.name,
                            "language": ext,
                            "size_bytes": p.stat().st_size,
                            "content": content,
                        })
                    except Exception:
                        pass

    return {
        "project": project.to_dict(),
        "files": file_list,
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


@router.get("/{project_id}/state")
async def get_project_state(
    project_id: str,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve the workflow state for a project."""
    # Ensure project exists and belongs to user
    res = await db.execute(select(Project).where(Project.id == project_id, Project.owner_id == user.id))
    project = res.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    wf_res = await db.execute(
        select(WorkflowState).where(
            WorkflowState.entity_type == "project",
            WorkflowState.entity_id == project_id,
            WorkflowState.owner_id == user.id,
        )
    )
    wf = wf_res.scalar_one_or_none()
    if not wf:
        # Create default workflow state if missing
        wf = WorkflowState(
            entity_type="project",
            entity_id=project_id,
            owner_id=user.id,
            state="planning",
            current_step="opportunity",
            operating_mode=user.operating_mode,
            step_data={"stage": "opportunity", "stages_completed": ["opportunity"]},
        )
        db.add(wf)
        await db.commit()
        await db.refresh(wf)

    return {"workflow": wf.to_dict(), "state": wf.to_dict(), "project_status": project.status}


@router.post("/{project_id}/advance")
async def advance_project_workflow(
    project_id: str,
    body: AdvanceWorkflowRequest,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Advance the project workflow through stages (opportunity -> architecture -> plan -> execution -> review)."""
    res = await db.execute(select(Project).where(Project.id == project_id, Project.owner_id == user.id))
    project = res.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    wf_res = await db.execute(
        select(WorkflowState).where(
            WorkflowState.entity_type == "project",
            WorkflowState.entity_id == project_id,
            WorkflowState.owner_id == user.id,
        )
    )
    wf = wf_res.scalar_one_or_none()
    if not wf:
        wf = WorkflowState(
            entity_type="project",
            entity_id=project_id,
            owner_id=user.id,
            state="planning",
            current_step="opportunity",
            operating_mode=user.operating_mode,
            step_data={"stage": "opportunity", "stages_completed": ["opportunity"]},
        )
        db.add(wf)

    stages = ["opportunity", "architecture", "plan", "execution", "review"]
    current_data = wf.step_data or {}
    current_stage = current_data.get("stage", "opportunity")
    completed = list(current_data.get("stages_completed", [current_stage]))

    if body.target_stage and body.target_stage in stages:
        next_stage = body.target_stage
    else:
        try:
            curr_idx = stages.index(current_stage)
            next_idx = min(curr_idx + 1, len(stages) - 1)
            next_stage = stages[next_idx]
        except ValueError:
            next_stage = "architecture"

    if next_stage not in completed:
        completed.append(next_stage)

    wf.previous_state = wf.state
    wf.state = "in_progress" if next_stage in ("execution", "plan") else "planning"
    wf.current_step = next_stage
    wf.step_data = {
        "stage": next_stage,
        "stages_completed": completed,
        "advanced_at": datetime.now(timezone.utc).isoformat(),
    }
    project.status = wf.state
    project.updated_at = datetime.now(timezone.utc)

    log = AuditLog(
        user_id=user.id,
        project_id=project_id,
        action="advance_workflow",
        category="project",
        description=f"Workflow advanced from {current_stage} to {next_stage}",
    )
    db.add(log)

    await db.commit()
    await db.refresh(wf)
    await db.refresh(project)

    return {
        "workflow": wf.to_dict(),
        "state": wf.to_dict(),
        "current_stage": next_stage,
        "stages_completed": completed,
        "project": project.to_dict(),
        "message": f"Project advanced to {next_stage} stage",
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
