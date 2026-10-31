"""
ProblemPilot AI — Master Autonomous Agent Orchestrator
Coordinates the complete end-to-end user journey:
ONE PROMPT → LIVE RESEARCH → PROBLEM VALIDATION → OPPORTUNITY SELECTION →
PROJECT DESIGN → BUILD → TEST → GITHUB → DEPLOY.
Supports Autonomous, Guided, and Hybrid execution modes with enforced approval checkpoints.
"""
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.config import settings
from backend.models.user import User
from backend.models.project import Project, ProjectFile
from backend.models.research import ResearchSession, ProblemCandidate, ResearchSource
from backend.models.approval import Approval, WorkflowState
from backend.services.research_agent import ResearchAgent
from backend.services.opportunity_engine import OpportunityEngine
from backend.services.approval_engine import ApprovalEngine
from backend.services.project_architect import ProjectArchitect
from backend.services.workspace_builder import WorkspaceBuilder
from backend.services.ai_teacher import AITeacher
from backend.services.github_service import GitHubService
from backend.services.cloud_deployer import CloudDeployer

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Master orchestrator executing multi-step agent actions with permission checkpoints.
    """

    def __init__(self):
        self.research_agent = ResearchAgent()
        self.opportunity_engine = OpportunityEngine()
        self.approval_engine = ApprovalEngine()
        self.project_architect = ProjectArchitect()
        self.workspace_builder = WorkspaceBuilder()
        self.ai_teacher = AITeacher()
        self.github_service = GitHubService()
        self.cloud_deployer = CloudDeployer()

    async def execute_prompt_journey(
        self,
        db: AsyncSession,
        user: User,
        prompt: str,
    ) -> Dict[str, Any]:
        """
        Execute Stage 1 & 2: Research & Opportunity Intelligence from one prompt.
        """
        # 1. Create ResearchSession
        intent = self.research_agent.parse_user_prompt(prompt)
        session = ResearchSession(
            owner_id=user.id,
            query=prompt,
            domain=intent.get("domain", ""),
            geography=intent.get("geography", ""),
            status="searching",
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)

        # 2. Execute Live Multi-source Research
        research_data = await self.research_agent.execute_live_research(prompt)

        # 3. Store sources
        session.status = "analyzing"
        await db.commit()

        for s in research_data.get("sources", []):
            source = ResearchSource(
                session_id=session.id,
                url=s.get("url", ""),
                title=s.get("title", ""),
                publisher=s.get("publisher", ""),
                snippet=s.get("snippet", ""),
                full_text=s.get("full_text", ""),
                relevance_score=s.get("relevance_score", 5.0),
                reliability=s.get("reliability", "medium"),
                source_type=s.get("source_type", "web"),
            )
            db.add(source)

        await db.commit()

        # 4. Rank and Synthesize 3-5 distinct opportunities
        ranked_opps = await self.opportunity_engine.rank_and_synthesize_opportunities(research_data)

        candidates = []
        for i, opp in enumerate(ranked_opps, 1):
            scores = opp.get("scores", {})
            prob = ProblemCandidate(
                session_id=session.id,
                title=opp.get("title", ""),
                description=f"{opp.get('summary', '')}\n\nProposed Solution: {opp.get('proposed_solution', '')}",
                affected_users=opp.get("affected_users", ""),
                existing_solutions=opp.get("existing_solutions", ""),
                solution_gaps=opp.get("key_differentiator", ""),
                evidence_summary=f"Discovered across {len(opp.get('evidence_sources', []))} real-world sources and community discussions.",
                claim_type="source_backed",
                scores=scores,
                overall_score=scores.get("overall_score", 7.5),
                rank=i,
                status="evaluated",
            )
            db.add(prob)
            candidates.append(prob)

        session.status = "completed"
        await db.commit()

        return {
            "session_id": session.id,
            "intent": intent,
            "total_sources": len(research_data.get("sources", [])),
            "opportunities_found": len(candidates),
            "opportunities": [c.to_dict() for c in candidates],
            "operating_mode": user.operating_mode,
            "next_checkpoint": {
                "action": "select_opportunity",
                "message": "Review and select an opportunity to proceed to architectural blueprint generation.",
            },
        }

    async def generate_blueprint_stage(
        self,
        db: AsyncSession,
        user: User,
        project_id: str,
    ) -> Dict[str, Any]:
        """
        Stage 5: Generate Tailored Project Blueprint.
        """
        res = await db.execute(select(Project).where(Project.id == project_id, Project.owner_id == user.id))
        project = res.scalar_one_or_none()
        if not project:
            raise ValueError("Project not found")

        blueprint = await self.project_architect.generate_blueprint(project.name, project.description)
        project.blueprint = blueprint
        project.tech_stack = blueprint.get("tech_stack", {})
        project.status = "planning"

        # Advance workflow state
        wf = await self.approval_engine.get_or_create_workflow(db, project.id, user.id, "project", user.operating_mode)
        wf.state = "planning"
        wf.current_step = "project_design"
        wf.step_data = {"stage": "project_design", "blueprint_ready": True}

        await db.commit()
        await db.refresh(project)

        # Check approval requirement based on mode
        approval_needed = (user.operating_mode in ("autonomous", "guided", "hybrid"))
        approval = None
        if approval_needed:
            approval = await self.approval_engine.request_approval(
                db=db,
                user_id=user.id,
                action_type="approve_architecture",
                project_id=project.id,
                title=f"Approve Architecture: {project.name}",
                description="Review system design, database schemas, and API contracts before generating code files.",
                proposed_action={"blueprint": blueprint},
            )

        return {
            "project_id": project.id,
            "blueprint": blueprint,
            "approval_required": bool(approval),
            "approval_id": approval.id if approval else None,
        }

    async def build_workspace_stage(
        self,
        db: AsyncSession,
        user: User,
        project_id: str,
        force_build: bool = False,
    ) -> Dict[str, Any]:
        """
        Stage 6: Generate Code in Isolated Sandbox Workspace.
        Enforces human-in-the-loop approval check before writing files.
        """
        res = await db.execute(select(Project).where(Project.id == project_id, Project.owner_id == user.id))
        project = res.scalar_one_or_none()
        if not project:
            raise ValueError("Project not found")

        # In Guided mode: show mentor instructions unless explicit build is authorized
        if user.operating_mode == "guided" and not force_build:
            return {
                "project_id": project.id,
                "mode": "guided",
                "mentor_instructions": {
                    "step_1": "Create index.html using semantic HTML5 and link styles.css.",
                    "step_2": "Implement FastAPI server in server.py exposing /api/v1/health.",
                    "step_3": "Add automated test cases in test_suite.py verifying status codes.",
                },
                "message": "Guided Mode active: Follow mentor instructions to code modules yourself or request assistance.",
            }

        # Check approval in Hybrid mode (Autonomous prepares code automatically)
        if user.operating_mode == "hybrid" and not force_build:
            action_params = {"project_id": project.id, "project_name": project.name}
            approved = await self.approval_engine.verify_approved(
                db=db,
                user_id=user.id,
                action_type="generate_workspace",
                project_id=project.id,
                action_params=action_params,
            )
            if not approved:
                # Check if architecture was approved previously
                arch_approved = await self.approval_engine.verify_approved(
                    db=db,
                    user_id=user.id,
                    action_type="approve_architecture",
                    project_id=project.id,
                )
                if not arch_approved:
                    approval = await self.approval_engine.request_approval(
                        db=db,
                        user_id=user.id,
                        action_type="generate_workspace",
                        project_id=project.id,
                        title=f"Generate Code Workspace: {project.name}",
                        description=f"Generate full-stack source code files into isolated project sandbox.",
                        proposed_action={"project_name": project.name, "tech_stack": project.tech_stack},
                        action_params=action_params,
                    )
                    return {
                        "project_id": project.id,
                        "approval_required": True,
                        "approval": approval.to_dict(),
                        "message": "Approval required before generating project files.",
                    }

            # Consume the approval atomically
            consume_action = "generate_workspace" if approved else "approve_architecture"
            consume_params = action_params if approved else None
            await self.approval_engine.consume_approval(
                db=db,
                user_id=user.id,
                action_type=consume_action,
                project_id=project.id,
                action_params=consume_params,
            )

        # Build files
        result = await self.workspace_builder.build_and_persist_workspace(
            db=db,
            project_id=project.id,
            project_name=project.name,
            blueprint=project.blueprint or {},
        )

        wf = await self.approval_engine.get_or_create_workflow(db, project.id, user.id, "project", user.operating_mode)
        wf.state = "in_progress"
        wf.current_step = "build_workspace"
        project.status = "in_progress"
        await db.commit()

        return {
            "project_id": project.id,
            "workspace_dir": result["workspace_dir"],
            "files_generated": result["files_written"],
            "message": f"Successfully generated {result['total_files']} files in isolated workspace.",
        }

    async def test_workspace_stage(
        self,
        db: AsyncSession,
        user: User,
        project_id: str,
    ) -> Dict[str, Any]:
        """
        Stage 7: Execute Automated Tests in Sandbox.
        """
        res = await db.execute(select(Project).where(Project.id == project_id, Project.owner_id == user.id))
        project = res.scalar_one_or_none()
        if not project:
            raise ValueError("Project not found")

        workspace_dir = self.workspace_builder.get_workspace_dir(project.id, project.name)

        # If files have not been generated yet, automatically build the workspace codebase first
        server_file = workspace_dir / "server.py"
        if not server_file.exists():
            await self.workspace_builder.build_and_persist_workspace(
                db=db,
                project_id=project.id,
                project_name=project.name,
                blueprint=project.blueprint or {},
            )

        test_results = await self.workspace_builder.run_workspace_tests(workspace_dir)

        wf = await self.approval_engine.get_or_create_workflow(db, project.id, user.id, "project", user.operating_mode)
        wf.current_step = "test_verification"
        if test_results.get("passed"):
            project.status = "verified"
            wf.state = "review"
            wf.current_step = "deployment"

        await db.commit()
        await db.refresh(project)

        return {
            "project_id": project.id,
            "test_results": test_results,
        }

    async def push_github_stage(
        self,
        db: AsyncSession,
        user: User,
        project_id: str,
        token: Optional[str] = None,
        repo_name: Optional[str] = None,
        private: bool = True,
    ) -> Dict[str, Any]:
        """
        Stage 8: Scan for secrets, create repo, and push code to GitHub.
        Enforces human-in-the-loop approval before remote creation and code push.
        """
        res = await db.execute(select(Project).where(Project.id == project_id, Project.owner_id == user.id))
        project = res.scalar_one_or_none()
        if not project:
            raise ValueError("Project not found")

        auth_token = token or user.get_github_token() or settings.GITHUB_PERSONAL_ACCESS_TOKEN
        if not auth_token:
            return {
                "success": False,
                "configured": False,
                "error": "GitHub authorization missing. Please connect your GitHub account via OAuth in Cloud & GitHub settings or provide a token.",
            }

        workspace_dir = self.workspace_builder.get_workspace_dir(project.id, project.name)
        target_name = repo_name or project.github_repo_name or project.name.lower().replace(" ", "-")

        # 1. Scan files recursively for exposed secrets
        EXCLUDE_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache"}
        MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB limit
        files_to_scan = {}
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
                        if p.stat().st_size <= MAX_FILE_SIZE:
                            files_to_scan[rel.as_posix()] = p.read_text(encoding="utf-8", errors="ignore")
                    except Exception:
                        pass

        if not files_to_scan:
            return {
                "success": False,
                "error": "Workspace has no source files to publish. Generate codebase first.",
            }

        secret_findings = self.github_service.scan_files_for_secrets(files_to_scan)
        if secret_findings:
            return {
                "success": False,
                "error": "Secret scan failed. Exposed credentials detected in project files.",
                "findings": secret_findings,
            }

        # 2. Enforce human-in-the-loop approval
        action_params = {"repo_name": target_name, "private": private}
        approved = await self.approval_engine.verify_approved(
            db=db,
            user_id=user.id,
            action_type="push_github_code",
            project_id=project.id,
            action_params=action_params,
        )
        if not approved:
            approval = await self.approval_engine.request_approval(
                db=db,
                user_id=user.id,
                action_type="push_github_code",
                project_id=project.id,
                title=f"Push to GitHub: {target_name} ({'Private' if private else 'Public'})",
                description=f"Create repository '{target_name}' on GitHub and push {len(files_to_scan)} project files.",
                proposed_action={
                    "repository_name": target_name,
                    "visibility": "private" if private else "public",
                    "files_to_upload": list(files_to_scan.keys()),
                    "secret_scan_status": "Clean (0 exposed secrets)",
                },
                action_params=action_params,
                risks="Creates remote repository and commits code under your GitHub profile.",
            )
            return {
                "approval_required": True,
                "approval": approval.to_dict(),
                "message": f"Approval required before pushing to GitHub repository '{target_name}'.",
            }

        # Consume approval atomically to prevent replay
        await self.approval_engine.consume_approval(
            db=db,
            user_id=user.id,
            action_type="push_github_code",
            project_id=project.id,
            action_params=action_params,
        )

        # 3. Create remote repository
        repo_res = await self.github_service.create_remote_repository(
            token=auth_token,
            repo_name=target_name,
            description=project.description or f"{project.name} — built with ProblemPilot AI",
            private=private,
        )
        if not repo_res.get("success"):
            return repo_res

        # 4. Commit and push
        push_res = await self.github_service.commit_and_push_to_github(
            workspace_dir=workspace_dir,
            repo_clone_url=repo_res.get("clone_url") or repo_res.get("repo_url"),
            token=auth_token,
        )
        if not push_res.get("success"):
            return push_res

        project.github_repo_url = repo_res.get("repo_url")
        project.github_repo_name = target_name
        project.github_branch = "main"

        wf = await self.approval_engine.get_or_create_workflow(db, project.id, user.id, "project", user.operating_mode)
        wf.current_step = "github_sync"
        await db.commit()

        return {
            "success": True,
            "repo_url": repo_res.get("repo_url"),
            "full_name": repo_res.get("full_name"),
            "branch": "main",
            "remote_verified": push_res.get("remote_verified", True),
            "message": "Project verified and pushed to remote GitHub repository.",
        }

    async def deploy_cloud_stage(
        self,
        db: AsyncSession,
        user: User,
        project_id: str,
        provider: str = "vercel",
        provider_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Stage 9: Enforce deployment approval and execute authentic cloud deployment.
        """
        res = await db.execute(select(Project).where(Project.id == project_id, Project.owner_id == user.id))
        project = res.scalar_one_or_none()
        if not project:
            raise ValueError("Project not found")

        workspace_dir = self.workspace_builder.get_workspace_dir(project.id, project.name)
        action_params = {"provider": provider}

        # 1. Enforce human-in-the-loop approval
        approved = await self.approval_engine.verify_approved(
            db=db,
            user_id=user.id,
            action_type="deploy_cloud",
            project_id=project.id,
            action_params=action_params,
        )
        if not approved:
            provider_details = self.cloud_deployer.get_provider_details(provider)
            # Generate deployment manifests so the user can inspect what will be deployed
            manifests = self.cloud_deployer.generate_deployment_manifests(workspace_dir, project.name)
            approval = await self.approval_engine.request_approval(
                db=db,
                user_id=user.id,
                action_type="deploy_cloud",
                project_id=project.id,
                title=f"Deploy Project to Cloud: {provider_details['name']}",
                description=f"Deploy application server and frontend to {provider.capitalize()}.",
                proposed_action={
                    "provider": provider,
                    "target_type": provider_details["target_type"],
                    "expected_cost": provider_details["expected_cost"],
                    "required_env_vars": provider_details["env_vars_needed"],
                    "manifests": list(manifests.keys()),
                },
                action_params=action_params,
                costs=provider_details["expected_cost"],
                risks="Creates live public HTTP deployment.",
            )
            return {
                "approval_required": True,
                "approval": approval.to_dict(),
                "manifests_generated": list(manifests.keys()),
                "message": f"Approval required before deploying to {provider.capitalize()}.",
            }

        # Consume approval atomically to prevent replay
        await self.approval_engine.consume_approval(
            db=db,
            user_id=user.id,
            action_type="deploy_cloud",
            project_id=project.id,
            action_params=action_params,
        )

        # 2. Execute authentic cloud provider deployment
        deploy_res = await self.cloud_deployer.execute_cloud_deployment(
            workspace_dir=workspace_dir,
            project_name=project.name,
            provider=provider,
            provider_token=provider_token,
        )

        project.deploy_provider = provider
        project.deploy_status = "deployed" if deploy_res.get("success") else "failed"
        if deploy_res.get("deploy_url"):
            project.deploy_url = deploy_res["deploy_url"]
        from datetime import datetime, timezone
        project.last_deploy_at = datetime.now(timezone.utc)

        # Track persistent deployment history
        from backend.models.deployment import Deployment
        from backend.models.audit import AuditLog

        dep_record = Deployment(
            project_id=project.id,
            owner_id=user.id,
            provider=provider,
            deployment_id=deploy_res.get("deployment_id"),
            deploy_url=deploy_res.get("deploy_url"),
            status="ready" if deploy_res.get("success") else "failed",
            error_details=deploy_res.get("error"),
            manifests_generated=deploy_res.get("manifests_generated", []),
            health_check_result=deploy_res.get("health_check", {}),
            verified_at=datetime.now(timezone.utc) if deploy_res.get("health_check", {}).get("verified") else None,
        )
        db.add(dep_record)

        audit_entry = AuditLog(
            user_id=user.id,
            project_id=project.id,
            action=f"cloud_deploy_{provider}",
            category="deployment",
            description=f"Cloud deployment to {provider}: status={project.deploy_status}, url={project.deploy_url}",
        )
        db.add(audit_entry)

        wf = await self.approval_engine.get_or_create_workflow(db, project.id, user.id, "project", user.operating_mode)
        wf.current_step = "cloud_deploy"
        await db.commit()

        return {
            "project_id": project.id,
            **deploy_res,
        }

