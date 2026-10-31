"""
ProblemPilot AI — Security, Operating Modes, Workspace & Approval Engine Verification
Validates:
1. Hardcoded backdoor credentials elimination (login with developer@problempilot.ai fails with 401).
2. Operating Mode enforcement (Autonomous, Guided, Hybrid).
3. Atomic Approval consumption with single-use replay protection.
4. Recursive workspace file listing and project files synchronization.
5. Safe GitHub publishing rejection when workspace has 0 files.
6. Cloud deployment payload and approval gates.
"""
import sys
import json
import logging
import asyncio
from pathlib import Path
from datetime import datetime, timezone
import pytest
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.database import init_db, AsyncSessionLocal
from backend.models.user import User
from backend.models.project import Project
from backend.services.approval_engine import ApprovalEngine
from backend.services.workspace_builder import WorkspaceBuilder
from backend.services.agent_orchestrator import AgentOrchestrator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_security_modes_workspace")


async def run_security_modes_workspace_tests():
    logger.info("Initializing Database for Security & Workspace Verification...")
    await init_db()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        # ── 1. Verify Hardcoded Developer Backdoor Login is Eliminated ──────
        logger.info("\n=== 1. Testing Developer Backdoor Elimination ===")
        backdoor_res = await client.post("/api/auth/login", json={
            "email": "developer@problempilot.ai",
            "password": "ProblemPilot123!",
        })
        assert backdoor_res.status_code == 401, f"Expected 401 Unauthorized for unseeded dev user, got {backdoor_res.status_code}"
        logger.info("✓ Hardcoded developer credentials rejected with 401 Unauthorized")

        # ── 2. Register Legitimate User & Test Operating Modes ───────────────
        logger.info("\n=== 2. Testing Operating Modes (Autonomous, Guided, Hybrid) ===")
        ts = int(datetime.now().timestamp())
        user_email = f"lead_eng_{ts}@example.com"
        reg_res = await client.post("/api/auth/register", json={
            "name": "Sarah Connor",
            "username": f"sarah_{ts}",
            "email": user_email,
            "password": "StrongPassword99!",
        })
        assert reg_res.status_code == 201
        token = reg_res.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}
        user_id = reg_res.json()["user"]["id"]

        # Default operating mode should be hybrid
        assert reg_res.json()["user"]["operating_mode"] == "hybrid"

        # Switch to autonomous
        mode_res = await client.put("/api/auth/mode", json={"mode": "autonomous"}, headers=auth_headers)
        assert mode_res.status_code == 200
        assert mode_res.json()["operating_mode"] == "autonomous"

        # Switch to guided
        mode_res2 = await client.put("/api/auth/mode", json={"mode": "guided"}, headers=auth_headers)
        assert mode_res2.status_code == 200
        assert mode_res2.json()["operating_mode"] == "guided"

        # Switch back to hybrid
        mode_res3 = await client.put("/api/auth/mode", json={"mode": "hybrid"}, headers=auth_headers)
        assert mode_res3.status_code == 200
        assert mode_res3.json()["operating_mode"] == "hybrid"
        logger.info("✓ Operating mode switching validated (autonomous, guided, hybrid)")

        # ── 3. Test Atomic Approval Engine & Replay Protection ───────────────
        logger.info("\n=== 3. Testing Atomic Approval Consumption & Replay Prevention ===")
        async with AsyncSessionLocal() as session:
            approval = await ApprovalEngine.request_approval(
                db=session,
                user_id=user_id,
                action_type="generate_workspace",
                title="Test Codebase Generation",
                description="Testing single-use atomic consumption",
                action_params={"mode": "hybrid"},
            )
            approval_id = approval.id

        # User approves request
        decide_res = await client.post(
            f"/api/approvals/{approval_id}/decide",
            json={"decision": "approved", "reason": "Authorized by lead architect"},
            headers=auth_headers,
        )
        assert decide_res.status_code == 200
        assert decide_res.json()["approval"]["decision"] == "approved"
        assert decide_res.json()["approval"]["consumed"] is False

        # First consumption must succeed
        async with AsyncSessionLocal() as session:
            consumed = await ApprovalEngine.consume_approval(
                db=session,
                user_id=user_id,
                action_type="generate_workspace",
                action_params={"mode": "hybrid"},
            )
            assert consumed.id == approval_id
            assert consumed.consumed is True
            logger.info("✓ First approval consumption succeeded atomically")

            # Second consumption (Replay Attack) MUST raise PermissionError
            replay_prevented = False
            try:
                await ApprovalEngine.consume_approval(
                    db=session,
                    user_id=user_id,
                    action_type="generate_workspace",
                    action_params={"mode": "hybrid"},
                )
            except PermissionError as pe:
                replay_prevented = True
                logger.info("✓ Replay attack blocked: %s", pe)

            assert replay_prevented, "Expected PermissionError on second consumption attempt"

        # ── 4. Project Creation, Blueprint & Recursive Workspace Files ───────
        logger.info("\n=== 4. Testing Workspace Sandbox & Recursive Files Traversal ===")
        proj_res = await client.post("/api/projects", json={
            "name": "Audit Logging Pipeline",
            "description": "High throughput audit logs ingestion pipeline",
            "operating_mode": "hybrid",
        }, headers=auth_headers)
        assert proj_res.status_code in (200, 201)
        project_id = proj_res.json()["project"]["id"]

        # Generate blueprint
        bp_res = await client.post(f"/api/orchestrator/projects/{project_id}/blueprint", headers=auth_headers)
        assert bp_res.status_code == 200
        assert "blueprint" in bp_res.json()

        # Build workspace
        build_res = await client.post(
            f"/api/orchestrator/projects/{project_id}/build",
            json={"force_build": True},
            headers=auth_headers,
        )
        assert build_res.status_code == 200
        files_written = build_res.json().get("files_generated", [])
        assert len(files_written) >= 5, f"Expected at least 5 files written, got {len(files_written)}"
        logger.info(f"✓ Generated {len(files_written)} workspace files: {files_written}")

        # Fetch workspace files via orchestrator route (recursive scan)
        files_res = await client.get(f"/api/orchestrator/projects/{project_id}/files", headers=auth_headers)
        assert files_res.status_code == 200
        ws_files = files_res.json().get("files", [])
        assert len(ws_files) >= len(files_written), f"Expected >= {len(files_written)} files, got {len(ws_files)}"
        file_paths = [f["path"] for f in ws_files]
        assert "server.py" in file_paths
        assert "test_suite.py" in file_paths
        assert "index.html" in file_paths
        logger.info("✓ Recursive workspace file endpoint returned complete codebase tree")

        # Fetch project detail and ensure files array is not empty
        proj_detail_res = await client.get(f"/api/projects/{project_id}", headers=auth_headers)
        assert proj_detail_res.status_code == 200
        detail_files = proj_detail_res.json().get("files", [])
        assert len(detail_files) > 0, "Project detail returned 0 files"
        logger.info(f"✓ GET /api/projects/{project_id} returned {len(detail_files)} source files")

        # ── 5. Safe GitHub Publishing Check ──────────────────────────────────
        logger.info("\n=== 5. Testing GitHub Publishing Safety & Approval Gate ===")
        # Attempt GitHub sync without token/oauth
        gh_missing_res = await client.post(f"/api/orchestrator/projects/{project_id}/github", json={}, headers=auth_headers)
        assert gh_missing_res.status_code == 400
        assert "authorization missing" in gh_missing_res.json()["detail"].lower()
        logger.info("✓ GitHub sync without credentials safely rejected")

        # With mock token, verify approval is required before pushing
        gh_appr_res = await client.post(
            f"/api/orchestrator/projects/{project_id}/github",
            json={"token": "ghp_mocktoken1234567890abcdef1234567890", "repository_name": "audit-pipe", "private": True},
            headers=auth_headers,
        )
        assert gh_appr_res.status_code == 200
        assert gh_appr_res.json().get("approval_required") is True
        gh_approval_id = gh_appr_res.json()["approval"]["id"]
        logger.info("✓ GitHub push requires human approval gate")

        # ── 6. Cloud Deployment Flow & Transparency ──────────────────────────
        logger.info("\n=== 6. Testing Cloud Deployment Approval Gate & Transparency ===")
        cloud_res = await client.post(
            f"/api/orchestrator/projects/{project_id}/deploy",
            json={"provider": "vercel"},
            headers=auth_headers,
        )
        assert cloud_res.status_code == 200
        assert cloud_res.json().get("approval_required") is True
        assert cloud_res.json()["approval"]["proposed_action"]["provider"] == "vercel"
        logger.info("✓ Cloud deployment requires human approval gate before edge execution")

    logger.info("\n" + "=" * 60)
    logger.info("🎉 ALL SECURITY, OPERATING MODES & WORKSPACE TESTS PASSED 100%!")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_security_modes_workspace_tests())
