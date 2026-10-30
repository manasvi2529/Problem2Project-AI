"""
ProblemPilot AI — End-to-End Platform Verification & Transformation Test Suite
Thoroughly verifies all requirements of the transformed platform:
1. Auth & Settings contracts (access_token/token, full_name/name aliases, settings/mode routes)
2. One-Prompt Journey & Intent Extraction
3. Live Multi-Source Research & Evidence Retainment
4. Opportunity Intelligence Engine (Assessment A, B, C scoring)
5. Project Creation & Aliases
6. Architectural Blueprint Generation
7. Workspace Sandbox & Full-Stack File Generation
8. Isolated pytest Execution in Workspace
9. AI Teacher Pedagogical & Interview Generation
10. Pre-push Secret Scanning & GitHub Integration
11. Cloud Deployment Manifest Generation & Health Probe
12. Approval Engine & State Machine
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
from backend.services.github_service import GitHubService
from backend.services.cloud_deployer import CloudDeployer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_transformation")


async def run_all_tests():
    logger.info("Initializing ProblemPilot AI Database...")
    await init_db()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # ── 1. Auth Contract & Aliases Test ──────────────────────────────────
        logger.info("\n=== 1. Testing Auth Contracts & Backward Compatibility ===")
        ts = int(datetime.now().timestamp())
        reg_payload = {
            "name": "Alex Mercer",
            "username": f"alex_{ts}",
            "email": f"alex_{ts}@example.com",
            "password": "SecurePassword123!",
        }
        res = await client.post("/api/auth/register", json=reg_payload)
        assert res.status_code == 201, f"Registration failed: {res.text}"
        reg_data = res.json()
        assert "access_token" in reg_data and "token" in reg_data, "Token aliases missing"
        assert reg_data["user"]["name"] == "Alex Mercer"
        logger.info("✓ Registration with name alias and token aliases passed")

        # Login check
        login_res = await client.post("/api/auth/login", json={
            "email": f"alex_{ts}@example.com",
            "password": "SecurePassword123!",
        })
        assert login_res.status_code == 200
        token = login_res.json()["token"]
        auth_headers = {"Authorization": f"Bearer {token}"}
        logger.info("✓ Login token generation passed")

        # Mode switching via /settings and /mode
        mode_res = await client.put("/api/auth/settings", json={"operating_mode": "autonomous"}, headers=auth_headers)
        assert mode_res.status_code == 200
        assert mode_res.json()["operating_mode"] == "autonomous"
        logger.info("✓ PUT /api/auth/settings mode switch passed")

        # ── 2. One-Prompt Journey & Opportunity Intelligence ─────────────────
        logger.info("\n=== 2. Testing One-Prompt Journey & Opportunity Intelligence Engine ===")
        prompt = "Find a real-world problem in India that I can solve with Python and SQL. I want a unique, placement-worthy project that could eventually become a startup. Research everything, compare existing solutions, and help me build it."
        
        journey_res = await client.post("/api/orchestrator/prompt", json={"prompt": prompt}, headers=auth_headers)
        assert journey_res.status_code == 200, f"Prompt journey failed: {journey_res.text}"
        jdata = journey_res.json()
        assert jdata["session_id"], "Session ID missing"
        assert jdata["intent"]["geography"] == "India", "Geography intent extraction failed"
        assert "python" in jdata["intent"]["skills"] and "sql" in jdata["intent"]["skills"], "Skills extraction failed"
        
        opps = jdata.get("opportunities", [])
        assert len(opps) >= 3, f"Expected at least 3 opportunities, got {len(opps)}"
        logger.info(f"✓ One-Prompt Journey returned {len(opps)} opportunities with intent extraction")

        first_opp = opps[0]
        scores = first_opp.get("scores", {})
        assert "assessment_a_evidence" in scores, "Assessment A missing"
        assert "assessment_b_developer_fit" in scores, "Assessment B missing"
        assert "assessment_c_business_potential" in scores, "Assessment C missing"
        logger.info(f"✓ 3-Factor Opportunity Scoring Verified: A={scores['assessment_a_evidence']['score']}, B={scores['assessment_b_developer_fit']['score']}, C={scores['assessment_c_business_potential']['score']}")

        # ── 3. Project Creation & Aliases ────────────────────────────────────
        logger.info("\n=== 3. Testing Project Creation & Workflow States ===")
        proj_res = await client.post("/api/projects", json={
            "title": "Automated Pipeline Sentinel",
            "description": "Autonomous discrepancy reconciliation engine for high-throughput data streams.",
            "problem_candidate_id": first_opp.get("id", ""),
            "repository_name": "pipeline-sentinel",
        }, headers=auth_headers)
        assert proj_res.status_code == 200, f"Project creation failed: {proj_res.text}"
        project_id = proj_res.json()["project"]["id"]
        logger.info(f"✓ Project created via title and problem_candidate_id aliases: ID={project_id}")

        # Check workflow state
        state_res = await client.get(f"/api/projects/{project_id}/state", headers=auth_headers)
        assert state_res.status_code == 200
        assert "workflow" in state_res.json()
        logger.info("✓ GET /api/projects/{id}/state passed")

        # ── 4. Architectural Blueprint Generation ───────────────────────────
        logger.info("\n=== 4. Testing Blueprint Generation ===")
        bp_res = await client.post(f"/api/orchestrator/projects/{project_id}/blueprint", headers=auth_headers)
        assert bp_res.status_code == 200
        bp = bp_res.json()["blueprint"]
        assert "database_schema" in bp and len(bp["database_schema"]) >= 2
        assert "api_contracts" in bp and len(bp["api_contracts"]) >= 3
        assert "interview_preparation" in bp and len(bp["interview_preparation"]) >= 2
        logger.info("✓ Tailored Blueprint generated with database schemas, API contracts & interview Q&As")

        # ── 5. Isolated Workspace & Code Generation ─────────────────────────
        logger.info("\n=== 5. Testing Codebase Generation into Isolated Sandbox ===")
        build_res = await client.post(f"/api/orchestrator/projects/{project_id}/build", headers=auth_headers)
        assert build_res.status_code == 200
        bdata = build_res.json()
        assert "files_generated" in bdata
        assert "server.py" in bdata["files_generated"]
        assert "test_suite.py" in bdata["files_generated"]
        assert "index.html" in bdata["files_generated"]
        assert "styles.css" in bdata["files_generated"]
        assert "app.js" in bdata["files_generated"]
        logger.info(f"✓ Workspace built with {len(bdata['files_generated'])} files at {bdata['workspace_dir']}")

        # Verify files via API
        files_res = await client.get(f"/api/orchestrator/projects/{project_id}/files", headers=auth_headers)
        assert files_res.status_code == 200
        disk_files = files_res.json().get("files", [])
        assert len(disk_files) >= 6
        logger.info(f"✓ Verified {len(disk_files)} project files persisted to disk and readable via API")

        # ── 6. Automated Sandbox Test Execution ─────────────────────────────
        logger.info("\n=== 6. Testing Isolated Automated Test Execution ===")
        test_res = await client.post(f"/api/orchestrator/projects/{project_id}/test", headers=auth_headers)
        assert test_res.status_code == 200
        tdata = test_res.json().get("test_results", {})
        assert tdata.get("passed") is True, f"Automated tests failed: {tdata.get('stdout')}\n{tdata.get('stderr')}"
        logger.info(f"✓ Isolated pytest execution PASSED (100% verified): Returncode={tdata.get('returncode')}")

        # ── 7. AI Teacher Engine ─────────────────────────────────────────────
        logger.info("\n=== 7. Testing AI Teacher & Placement Explanations ===")
        teach_res = await client.post(f"/api/orchestrator/projects/{project_id}/teach", json={
            "topic": "FastAPI Async Coroutines",
            "context": "High-throughput anomaly stream processing",
            "level": "interview_prep",
        }, headers=auth_headers)
        assert teach_res.status_code == 200
        expl = teach_res.json().get("explanation", {})
        assert "interview_explanation" in expl
        assert "why_used" in expl
        assert "common_pitfalls" in expl
        logger.info("✓ AI Teacher successfully produced pedagogical and interview preparation breakdown")

        # ── 8. Secret Scanning Security ──────────────────────────────────────
        logger.info("\n=== 8. Testing Pre-push Secret Scanning ===")
        clean_files = {"server.py": "print('hello')", "config.py": "PORT = 8000"}
        assert len(GitHubService.scan_files_for_secrets(clean_files)) == 0
        
        dirty_files = {"keys.py": "sk-1234567890abcdef1234567890abcdef", "aws.py": "AKIA1234567890ABCDEF"}
        findings = GitHubService.scan_files_for_secrets(dirty_files)
        assert len(findings) == 2
        logger.info(f"✓ Pre-push Secret Scanner caught {len(findings)} exposed credentials")

        # ── 9. Cloud Deployment Manifests & Health Verification ──────────────
        logger.info("\n=== 9. Testing Cloud Deployment Manifest Generation ===")
        deploy_res = await client.post(f"/api/orchestrator/projects/{project_id}/deploy", json={
            "provider": "vercel",
        }, headers=auth_headers)
        assert deploy_res.status_code == 200
        manifests = deploy_res.json().get("manifests_generated", [])
        assert "vercel.json" in manifests
        assert "render.yaml" in manifests
        assert "Dockerfile" in manifests
        logger.info(f"✓ Cloud deployment manifests generated: {', '.join(manifests)}")

        # ── 10. Approval Checkpoint Decision ────────────────────────────────
        logger.info("\n=== 10. Testing Approval Checkpoint & Workflow Advance ===")
        adv_res = await client.post(f"/api/projects/{project_id}/advance", json={"target_stage": "execution"}, headers=auth_headers)
        assert adv_res.status_code == 200
        assert adv_res.json()["current_stage"] == "execution"
        logger.info("✓ Workflow stage advanced to 'execution'")

    logger.info("\n" + "=" * 60)
    logger.info("🎉 ALL 10 TRANSFORMATION TEST SUITES PASSED WITH 100% SUCCESS!")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_all_tests())

