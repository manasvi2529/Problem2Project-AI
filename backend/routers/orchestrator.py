"""
ProblemPilot AI — Master Orchestrator Router
Unified endpoints powering the complete:
ONE PROMPT → LIVE RESEARCH → PROBLEM VALIDATION → OPPORTUNITY SELECTION →
PROJECT DESIGN → BUILD → TEST → GITHUB → DEPLOY
journey with live teaching, permissions, and cloud deployment.
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field

from backend.database import get_db
from backend.routers.auth import get_user_from_token
from backend.models.user import User
from backend.models.project import Project, ProjectFile
from backend.services.agent_orchestrator import AgentOrchestrator
from backend.services.approval_engine import ApprovalEngine
from backend.services.ai_teacher import AITeacher

router = APIRouter(prefix="/api/orchestrator", tags=["orchestrator"])
orchestrator = AgentOrchestrator()
teacher = AITeacher()


# ── Request Schemas ──────────────────────────────────────────────────────────

class PromptJourneyRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=1000)

class BuildWorkspaceRequest(BaseModel):
    force_build: Optional[bool] = False

class TestWorkspaceRequest(BaseModel):
    pass

class TeachRequest(BaseModel):
    topic: str
    context: Optional[str] = ""
    level: Optional[str] = "intermediate"

class GitHubSyncRequest(BaseModel):
    token: Optional[str] = None
    repository_name: Optional[str] = None
    private: Optional[bool] = True

class CloudDeployRequest(BaseModel):
    provider: Optional[str] = "vercel"
    provider_token: Optional[str] = None
    verify_url: Optional[str] = None


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/prompt")
async def start_prompt_journey(
    body: PromptJourneyRequest,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """
    Execute ONE PROMPT:
    Performs live multi-source research across communities and the web,
    validates user problems with Data Science metrics,
    and returns 3-5 ranked, evidence-backed opportunities.
    """
    try:
        result = await orchestrator.execute_prompt_journey(db, user, body.prompt)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Research journey failed: {str(e)}")


@router.post("/projects/{project_id}/blueprint")
async def generate_blueprint(
    project_id: str,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Generate complete project blueprint tailored to the selected problem."""
    try:
        return await orchestrator.generate_blueprint_stage(db, user, project_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/build")
async def build_project_workspace(
    project_id: str,
    body: Optional[BuildWorkspaceRequest] = None,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Generate actual full-stack source code into isolated project sandbox."""
    try:
        force = body.force_build if body else False
        return await orchestrator.build_workspace_stage(db, user, project_id, force_build=force)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/test")
async def test_project_workspace(
    project_id: str,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Run automated verification tests in sandbox and return actual results."""
    try:
        return await orchestrator.test_workspace_stage(db, user, project_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/teach")
async def teach_concept(
    project_id: str,
    body: TeachRequest,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """AI Teacher explanation grounded in actual project code, architecture, and interview prep."""
    res = await db.execute(select(Project).where(Project.id == project_id, Project.owner_id == user.id))
    project = res.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Load actual workspace files recursively if available
    workspace_dir = orchestrator.workspace_builder.get_workspace_dir(project.id, project.name)
    files_context = {}
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
                    files_context[rel.as_posix()] = p.read_text(encoding="utf-8", errors="ignore")[:600]
                except Exception:
                    pass

    context = body.context or f"Project '{project.name}': {project.description or ''}"
    explanation = await teacher.explain_concept(
        topic=body.topic,
        context=context,
        level=body.level or "intermediate",
        project_name=project.name,
        files_context=files_context,
    )
    return {"explanation": explanation}


@router.post("/projects/{project_id}/github")
async def sync_github(
    project_id: str,
    body: GitHubSyncRequest,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Scan for secrets, create repo, and push code to GitHub."""
    result = await orchestrator.push_github_stage(
        db=db,
        user=user,
        project_id=project_id,
        token=body.token,
        repo_name=body.repository_name,
        private=bool(body.private),
    )
    if not result.get("success") and not result.get("approval_required"):
        raise HTTPException(status_code=400, detail=result.get("error", "GitHub sync failed"))
    return result


@router.post("/projects/{project_id}/deploy")
async def deploy_cloud(
    project_id: str,
    body: CloudDeployRequest,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Enforce deployment approval and execute authentic cloud deployment."""
    result = await orchestrator.deploy_cloud_stage(
        db=db,
        user=user,
        project_id=project_id,
        provider=body.provider or "vercel",
        provider_token=body.provider_token,
    )
    if body.verify_url:
        probe = await orchestrator.cloud_deployer.verify_remote_deployment(body.verify_url)
        result["verification"] = probe
    return result


@router.get("/projects/{project_id}/files")
async def get_workspace_files(
    project_id: str,
    user: User = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """List all source files from disk for the project workspace."""
    res = await db.execute(select(Project).where(Project.id == project_id, Project.owner_id == user.id))
    project = res.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    workspace_dir = orchestrator.workspace_builder.get_workspace_dir(project.id, project.name)
    files = []
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
                    files.append({
                        "name": p.name,
                        "path": rel.as_posix(),
                        "extension": ext,
                        "size_bytes": p.stat().st_size,
                        "content": content,
                    })
                except Exception:
                    pass

    return {"files": files, "workspace_dir": str(workspace_dir)}

