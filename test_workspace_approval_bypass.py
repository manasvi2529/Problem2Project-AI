"""
ProblemPilot AI — Focused Tests: Workspace-Generation Approval Bypass Prevention
Verifies:
1. Guided mode cannot generate files through the testing endpoint.
2. Hybrid mode cannot generate files without approval (even if force_build: True is passed).
3. Hybrid mode can proceed with valid approval and consumes it atomically.
4. Autonomous mode follows its intended generation path.
5. Testing an existing workspace does not unexpectedly regenerate it.
"""
import sys
import json
import logging
import asyncio
from pathlib import Path
from datetime import datetime
import pytest
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.database import init_db, AsyncSessionLocal
from backend.models.user import User
from backend.models.project import Project
from backend.models.approval import Approval
from backend.services.workspace_builder import WorkspaceBuilder
from sqlalchemy import select

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_workspace_approval_bypass")


async def run_tests():
    logger.info("Initializing database...")
    await init_db()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ts = int(datetime.now().timestamp())

        # ─────────────────────────────────────────────────────────────────────
        # 1. Guided Mode: Cannot generate files through testing endpoint
        # ─────────────────────────────────────────────────────────────────────
        logger.info("\n=== TEST 1: Guided mode cannot generate files through testing endpoint ===")
        guided_email = f"guided_{ts}@example.com"
        reg_res = await client.post("/api/auth/register", json={
            "name": "Guided Student",
            "username": f"guided_{ts}",
            "email": guided_email,
            "password": "Password123!",
        })
        assert reg_res.status_code == 201, f"Reg failed: {reg_res.text}"
        guided_token = reg_res.json()["access_token"]
        guided_headers = {"Authorization": f"Bearer {guided_token}"}

        # Set user mode to guided
        mode_res = await client.put("/api/auth/mode", json={"mode": "guided"}, headers=guided_headers)
        assert mode_res.status_code == 200
        assert mode_res.json()["operating_mode"] == "guided"

        # Create guided project
        proj_res = await client.post("/api/projects", json={
            "name": "Guided Learning Project",
            "description": "Student guided project for testing",
            "operating_mode": "guided",
        }, headers=guided_headers)
        assert proj_res.status_code in (200, 201)
        guided_proj_id = proj_res.json()["project"]["id"]

        # Ensure no workspace files exist
        workspace_builder = WorkspaceBuilder()
        guided_ws_dir = workspace_builder.get_workspace_dir(guided_proj_id, "Guided Learning Project")
        assert not (guided_ws_dir / "server.py").exists()

        # Call /test endpoint on ungenerated workspace
        test_res = await client.post(f"/api/orchestrator/projects/{guided_proj_id}/test", headers=guided_headers)
        assert test_res.status_code == 200
        tdata = test_res.json()
        assert tdata.get("code_generation_required") is True, f"Expected code_generation_required=True, got {tdata}"
        assert tdata.get("test_results", {}).get("status") == "not_generated"
        assert not (guided_ws_dir / "server.py").exists(), "Testing endpoint must NEVER generate source files"
        logger.info("✓ Guided mode cannot generate files through /test endpoint")

        # Also verify client passing force_build: True to /build does NOT silently generate files in Guided mode
        build_res = await client.post(
            f"/api/orchestrator/projects/{guided_proj_id}/build",
            json={"force_build": True},
            headers=guided_headers,
        )
        assert build_res.status_code == 200
        bdata = build_res.json()
        assert bdata.get("mode") == "guided"
        assert "mentor_instructions" in bdata
        assert not (guided_ws_dir / "server.py").exists(), "Guided mode must not silently generate files with force_build"
        logger.info("✓ Guided mode returns mentor instructions and ignores force_build flag without approval")

        # ─────────────────────────────────────────────────────────────────────
        # 2. Hybrid Mode: Cannot generate files without approval
        # ─────────────────────────────────────────────────────────────────────
        logger.info("\n=== TEST 2: Hybrid mode cannot generate files without approval ===")
        hybrid_email = f"hybrid_{ts}@example.com"
        reg_res2 = await client.post("/api/auth/register", json={
            "name": "Hybrid Architect",
            "username": f"hybrid_{ts}",
            "email": hybrid_email,
            "password": "Password123!",
        })
        assert reg_res2.status_code == 201
        hybrid_token = reg_res2.json()["access_token"]
        hybrid_headers = {"Authorization": f"Bearer {hybrid_token}"}

        # User is hybrid by default
        proj_res2 = await client.post("/api/projects", json={
            "name": "Hybrid Pipeline Project",
            "description": "Hybrid pipeline architecture for testing",
            "operating_mode": "hybrid",
        }, headers=hybrid_headers)
        assert proj_res2.status_code in (200, 201)
        hybrid_proj_id = proj_res2.json()["project"]["id"]
        hybrid_ws_dir = workspace_builder.get_workspace_dir(hybrid_proj_id, "Hybrid Pipeline Project")

        # Generate blueprint (creates pending approval)
        bp_res = await client.post(f"/api/orchestrator/projects/{hybrid_proj_id}/blueprint", headers=hybrid_headers)
        assert bp_res.status_code == 200
        assert bp_res.json()["approval_required"] is True

        # Attempt to build without approving, even with force_build: True
        unapproved_build = await client.post(
            f"/api/orchestrator/projects/{hybrid_proj_id}/build",
            json={"force_build": True},
            headers=hybrid_headers,
        )
        assert unapproved_build.status_code == 200
        ub_data = unapproved_build.json()
        assert ub_data.get("approval_required") is True, f"Expected approval_required=True, got {ub_data}"
        assert not (hybrid_ws_dir / "server.py").exists(), "Workspace files must not be written without approval"
        logger.info("✓ Hybrid mode blocked build without approval (force_build bypass prevented)")

        # Verify /test also does not generate files
        unapproved_test = await client.post(f"/api/orchestrator/projects/{hybrid_proj_id}/test", headers=hybrid_headers)
        assert unapproved_test.status_code == 200
        assert unapproved_test.json().get("code_generation_required") is True
        assert not (hybrid_ws_dir / "server.py").exists(), "Workspace files must not be generated via /test"
        logger.info("✓ Hybrid mode /test correctly requires code generation and does not write files")

        # ─────────────────────────────────────────────────────────────────────
        # 3. Hybrid Mode: Can proceed with valid approval
        # ─────────────────────────────────────────────────────────────────────
        logger.info("\n=== TEST 3: Hybrid mode proceeds with valid approval ===")
        # Get pending approvals
        app_res = await client.get("/api/approvals/pending", headers=hybrid_headers)
        assert app_res.status_code == 200
        approvals = app_res.json()["approvals"]
        proj_approvals = [a for a in approvals if a.get("project_id") == hybrid_proj_id]
        assert len(proj_approvals) >= 1, "Expected pending approval for hybrid project"
        target_approval_id = proj_approvals[0]["id"]

        # Approve the request
        decide_res = await client.post(
            f"/api/approvals/{target_approval_id}/decide",
            json={"decision": "approved", "reason": "Architecture reviewed and approved"},
            headers=hybrid_headers,
        )
        assert decide_res.status_code == 200
        assert decide_res.json()["approval"]["decision"] == "approved"

        # Now build the workspace
        approved_build = await client.post(
            f"/api/orchestrator/projects/{hybrid_proj_id}/build",
            headers=hybrid_headers,
        )
        assert approved_build.status_code == 200
        ab_data = approved_build.json()
        assert "files_generated" in ab_data
        assert "server.py" in ab_data["files_generated"]
        assert (hybrid_ws_dir / "server.py").exists()
        logger.info(f"✓ Hybrid mode proceeded with valid approval, generated {len(ab_data['files_generated'])} files")

        # Verify approval consumption: attempting another build requires a new approval
        second_build = await client.post(
            f"/api/orchestrator/projects/{hybrid_proj_id}/build",
            headers=hybrid_headers,
        )
        assert second_build.status_code == 200
        assert second_build.json().get("approval_required") is True, "Approval must be consumed (replay prevented)"
        logger.info("✓ Hybrid mode atomically consumed approval; replay attempt blocked")

        # ─────────────────────────────────────────────────────────────────────
        # 4. Autonomous Mode: Follows its intended generation path
        # ─────────────────────────────────────────────────────────────────────
        logger.info("\n=== TEST 4: Autonomous mode follows intended generation path ===")
        auto_email = f"auto_{ts}@example.com"
        reg_res3 = await client.post("/api/auth/register", json={
            "name": "Auto Developer",
            "username": f"auto_{ts}",
            "email": auto_email,
            "password": "Password123!",
        })
        assert reg_res3.status_code == 201
        auto_token = reg_res3.json()["access_token"]
        auto_headers = {"Authorization": f"Bearer {auto_token}"}

        # Switch mode to autonomous
        await client.put("/api/auth/mode", json={"mode": "autonomous"}, headers=auto_headers)

        proj_res3 = await client.post("/api/projects", json={
            "name": "Autonomous Agent Project",
            "description": "Full autonomous pipeline execution test",
            "operating_mode": "autonomous",
        }, headers=auto_headers)
        assert proj_res3.status_code in (200, 201)
        auto_proj_id = proj_res3.json()["project"]["id"]
        auto_ws_dir = workspace_builder.get_workspace_dir(auto_proj_id, "Autonomous Agent Project")

        # Blueprint
        await client.post(f"/api/orchestrator/projects/{auto_proj_id}/blueprint", headers=auto_headers)

        # Autonomous build proceeds directly per permitted workflow
        auto_build = await client.post(f"/api/orchestrator/projects/{auto_proj_id}/build", headers=auto_headers)
        assert auto_build.status_code == 200
        auto_data = auto_build.json()
        assert "files_generated" in auto_data
        assert (auto_ws_dir / "server.py").exists()
        logger.info(f"✓ Autonomous mode generated workspace files per permitted workflow ({len(auto_data['files_generated'])} files)")

        # ─────────────────────────────────────────────────────────────────────
        # 5. Testing an existing workspace does not unexpectedly regenerate it
        # ─────────────────────────────────────────────────────────────────────
        logger.info("\n=== TEST 5: Testing existing workspace does not unexpectedly regenerate it ===")
        server_path = auto_ws_dir / "server.py"
        canary_marker = "# CANARY_TEST_MARKER_DO_NOT_REWRITE"
        original_server_code = server_path.read_text(encoding="utf-8")
        server_path.write_text(original_server_code + f"\n{canary_marker}\n", encoding="utf-8")

        # Also write a custom canary file
        canary_file = auto_ws_dir / "canary_check.txt"
        canary_file.write_text("Canary content to verify testing does not wipe workspace", encoding="utf-8")

        # Call /test endpoint
        test_run = await client.post(f"/api/orchestrator/projects/{auto_proj_id}/test", headers=auto_headers)
        assert test_run.status_code == 200
        test_run_data = test_run.json()
        assert "test_results" in test_run_data

        # Verify canary marker is still in server.py
        current_server_code = server_path.read_text(encoding="utf-8")
        assert canary_marker in current_server_code, "Testing must NOT regenerate or overwrite server.py"

        # Verify canary file is intact
        assert canary_file.exists(), "Testing must NOT wipe or regenerate workspace directory"
        assert canary_file.read_text(encoding="utf-8") == "Canary content to verify testing does not wipe workspace"
        logger.info("✓ Testing existing workspace preserved existing code and canary files without regeneration")

    logger.info("\n============================================================")
    logger.info("🎉 ALL WORKSPACE APPROVAL BYPASS TESTS PASSED 100%!")
    logger.info("============================================================")


if __name__ == "__main__":
    asyncio.run(run_tests())

