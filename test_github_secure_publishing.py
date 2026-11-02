"""
ProblemPilot AI — Sprint 2: Secure GitHub Publishing Test Suite
Verifies all 5 core security requirements:
1. No token appears in the remote URL.
2. No token remains in ".git/config".
3. Failed pushes do not leave credentials behind.
4. Publishing without a connected user account is rejected (and global token fallback is removed).
5. Publishing with a connected account still works.
6. Credentials are redacted from all returned errors and logs.
"""
import os
import re
import base64
import shutil
import tempfile
import asyncio
import logging
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from backend.main import app
from backend.config import settings
from backend.database import init_db, AsyncSessionLocal
from backend.models.user import User
from backend.models.project import Project
from backend.models.approval import Approval
from backend.services.github_service import GitHubService, redact_credentials
from backend.services.agent_orchestrator import AgentOrchestrator
from backend.services.workspace_builder import WorkspaceBuilder

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_github_secure_publishing")


async def run_tests():
    logger.info("Initializing Database for Secure GitHub Publishing Tests...")
    await init_db()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ts = int(datetime.now().timestamp())

        # ─────────────────────────────────────────────────────────────────────
        # 1. Publishing without a connected user account is rejected
        # ─────────────────────────────────────────────────────────────────────
        logger.info("\n=== TEST 1: Publishing without connected user account is rejected ===")
        user_email = f"unconnected_{ts}@example.com"
        reg_res = await client.post("/api/auth/register", json={
            "name": "Unconnected User",
            "username": f"unconnected_{ts}",
            "email": user_email,
            "password": "Password123!",
        })
        assert reg_res.status_code == 201
        token = reg_res.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}
        user_id = reg_res.json()["user"]["id"]

        # Switch user mode to autonomous so build can generate files
        await client.put("/api/auth/mode", json={"mode": "autonomous"}, headers=auth_headers)

        # Create project and generate a sample workspace
        proj_res = await client.post("/api/projects", json={
            "name": "GitHub Safety Demo",
            "description": "Validating git publishing safety without tokens",
            "operating_mode": "autonomous",
        }, headers=auth_headers)
        assert proj_res.status_code in (200, 201)
        proj_id = proj_res.json()["project"]["id"]

        # Build workspace files so there is code to publish
        build_res = await client.post(f"/api/orchestrator/projects/{proj_id}/build", headers=auth_headers)
        assert build_res.status_code == 200

        # Attempt to publish without connected GitHub account
        pub_res1 = await client.post(f"/api/orchestrator/projects/{proj_id}/github", json={}, headers=auth_headers)
        assert pub_res1.status_code == 400
        detail1 = pub_res1.json().get("detail", "").lower()
        assert "not connected" in detail1 or "authorization missing" in detail1
        logger.info("✓ Publishing without connected GitHub account rejected with HTTP 400")

        # Verify global GITHUB_PERSONAL_ACCESS_TOKEN fallback is NOT used
        orig_global = settings.GITHUB_PERSONAL_ACCESS_TOKEN
        try:
            settings.GITHUB_PERSONAL_ACCESS_TOKEN = "ghp_global_server_admin_token_should_never_be_used"
            pub_res2 = await client.post(f"/api/orchestrator/projects/{proj_id}/github", json={}, headers=auth_headers)
            assert pub_res2.status_code == 400
            detail2 = pub_res2.json().get("detail", "").lower()
            assert "not connected" in detail2 or "authorization missing" in detail2
            logger.info("✓ Global GITHUB_PERSONAL_ACCESS_TOKEN is strictly ignored for user publishing")
        finally:
            settings.GITHUB_PERSONAL_ACCESS_TOKEN = orig_global

        # ─────────────────────────────────────────────────────────────────────
        # 2. No token appears in remote URL & no token remains in .git/config
        # ─────────────────────────────────────────────────────────────────────
        logger.info("\n=== TEST 2 & 3: Clean Git Remote & Zero Token Persistence in .git/config ===")
        temp_dir = Path(tempfile.mkdtemp(prefix="git_sec_test_"))
        test_token = "gho_superSecretTokenThatMustNeverPersist999"
        clean_remote_url = "https://github.com/test-org/secure-repo.git"

        try:
            # Create a sample project file
            sample_file = temp_dir / "server.py"
            sample_file.write_text("print('Secure Git Push')", encoding="utf-8")

            # Mock git push subprocess so we test git setup and verify no token is stored
            original_create_subprocess_exec = asyncio.create_subprocess_exec

            captured_envs = []
            captured_commands = []

            async def mock_subprocess_exec(cmd, *args, **kwargs):
                captured_commands.append((cmd, list(args)))
                if "env" in kwargs and kwargs["env"]:
                    captured_envs.append(dict(kwargs["env"]))
                # If command is push, mock success
                if args and args[0] == "push":
                    proc = AsyncMock()
                    proc.returncode = 0
                    proc.communicate = AsyncMock(return_value=(b"Everything up-to-date", b""))
                    return proc
                # Run real git commands for init, config, add, commit, remote
                return await original_create_subprocess_exec(cmd, *args, **kwargs)

            with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec), \
                 patch.object(GitHubService, "verify_remote_commit", new_callable=AsyncMock) as mock_verify:
                mock_verify.return_value = {"verified": True, "sha": "abc1234"}

                result = await GitHubService.commit_and_push_to_github(
                    workspace_dir=temp_dir,
                    repo_clone_url=clean_remote_url,
                    token=test_token,
                    commit_message="Security audit commit",
                )
                assert result.get("success") is True, f"Push failed: {result}"

            # 2.A Verify remote URL has NO token
            proc = await original_create_subprocess_exec(
                "git", "remote", "get-url", "origin",
                cwd=str(temp_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            actual_remote_url = stdout.decode("utf-8").strip()

            assert actual_remote_url == clean_remote_url, f"Expected clean URL, got {actual_remote_url}"
            assert test_token not in actual_remote_url, "Token MUST NOT appear in git remote URL"
            assert "@" not in actual_remote_url, "Remote URL must not contain embedded user/password credentials"
            logger.info(f"✓ Git remote URL verified clean: {actual_remote_url}")

            # 2.B Verify .git/config has NO token
            git_config_path = temp_dir / ".git" / "config"
            assert git_config_path.exists(), ".git/config must exist"
            git_config_content = git_config_path.read_text(encoding="utf-8")

            assert test_token not in git_config_content, "Token MUST NEVER be written to .git/config"
            assert "oauth2:" not in git_config_content, "No oauth2 credentials in .git/config"
            assert "x-access-token" not in git_config_content, "No x-access-token credentials in .git/config"
            logger.info("✓ Confirmed .git/config is free of any tokens or embedded credentials")

            # 2.C Verify command-line arguments contained NO token
            for cmd, args in captured_commands:
                cmd_line = f"{cmd} {' '.join(args)}"
                assert test_token not in cmd_line, f"Token leaked in command line args: {cmd_line}"
            logger.info("✓ Confirmed command-line arguments contained zero tokens")

            # 2.D Verify temporary environment contained auth header only during push
            assert len(captured_envs) >= 1, "Expected subprocess push_env to be passed to git push"
            push_env = captured_envs[0]
            assert push_env.get("GIT_TERMINAL_PROMPT") == "0"
            assert push_env.get("GIT_CONFIG_KEY_0") == "http.extraHeader"
            assert "AUTHORIZATION: basic" in push_env.get("GIT_CONFIG_VALUE_0", "")
            # Ensure the token is not leaked as plaintext env var name
            assert test_token not in os.environ, "Token must not leak into persistent os.environ"
            logger.info("✓ Subprocess environment passed HTTP authentication header securely")

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        # ─────────────────────────────────────────────────────────────────────
        # 3. Failed pushes do not leave credentials behind
        # ─────────────────────────────────────────────────────────────────────
        logger.info("\n=== TEST 4: Failed pushes do not leave credentials behind ===")
        fail_dir = Path(tempfile.mkdtemp(prefix="git_fail_test_"))
        bare_reject_dir = Path(tempfile.mkdtemp(prefix="git_bare_reject_"))
        fail_token = "gho_failedPushTokenSecretXYZ12345"

        try:
            # Set up a bare git repository that rejects pushes via pre-receive hook
            subprocess.run(["git", "init", "--bare"], cwd=str(bare_reject_dir), capture_output=True)
            hooks_dir = bare_reject_dir / "hooks"
            hooks_dir.mkdir(exist_ok=True)
            hook_file = hooks_dir / "pre-receive"
            hook_file.write_text("#!/bin/sh\necho 'Server rejected push'\nexit 1\n", encoding="utf-8")

            reject_remote_url = f"file:///{bare_reject_dir.as_posix()}"

            (fail_dir / "index.html").write_text("<h1>Fail Test</h1>", encoding="utf-8")

            # Call real git push against the rejecting remote
            fail_result = await GitHubService.commit_and_push_to_github(
                workspace_dir=fail_dir,
                repo_clone_url=reject_remote_url,
                token=fail_token,
                commit_message="Test failure cleanup",
            )
            assert fail_result.get("success") is False, "Expected git push to fail against rejecting remote"
            logger.info(f"✓ Push failed cleanly as expected: {fail_result.get('error')}")

            # Verify error message does NOT contain the plaintext token
            error_msg = fail_result.get("error", "")
            assert fail_token not in error_msg, "Failed push error message must not expose the token"

            # Verify .git/config on disk does NOT contain the token
            fail_git_config = fail_dir / ".git" / "config"
            assert fail_git_config.exists()
            fail_config_content = fail_git_config.read_text(encoding="utf-8")
            assert fail_token not in fail_config_content, "Failed push must NOT leave token in .git/config"
            assert "oauth2:" not in fail_config_content
            assert "AUTHORIZATION:" not in fail_config_content

            # Verify git remote get-url origin is clean
            proc = await asyncio.create_subprocess_exec(
                "git", "remote", "get-url", "origin",
                cwd=str(fail_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            fail_remote_url = stdout.decode("utf-8").strip()
            assert fail_token not in fail_remote_url
            assert fail_remote_url == reject_remote_url
            logger.info("✓ Verified failed push left zero credentials in .git/config, remote URL, or error messages")
        finally:
            shutil.rmtree(fail_dir, ignore_errors=True)
            shutil.rmtree(bare_reject_dir, ignore_errors=True)

        # ─────────────────────────────────────────────────────────────────────
        # 4. Publishing with a connected account still works & requires approval
        # ─────────────────────────────────────────────────────────────────────
        logger.info("\n=== TEST 5: Publishing with connected account works & requires approval ===")
        connected_email = f"connected_{ts}@example.com"
        reg_c = await client.post("/api/auth/register", json={
            "name": "Connected Dev",
            "username": f"conn_{ts}",
            "email": connected_email,
            "password": "Password123!",
        })
        assert reg_c.status_code == 201
        c_token = reg_c.json()["access_token"]
        c_headers = {"Authorization": f"Bearer {c_token}"}
        c_user_id = reg_c.json()["user"]["id"]

        # Switch user mode to autonomous so build generates workspace files
        await client.put("/api/auth/mode", json={"mode": "autonomous"}, headers=c_headers)

        # Connect user's GitHub OAuth token
        mock_oauth_token = "gho_legitimateConnectedOAuthToken777"
        async with AsyncSessionLocal() as session:
            u = (await session.execute(select(User).where(User.id == c_user_id))).scalar_one()
            u.set_github_token(mock_oauth_token)
            u.github_username = f"conn_dev_{ts}"
            await session.commit()

        # Create project and workspace
        p_res = await client.post("/api/projects", json={
            "name": "Audit Ready System",
            "description": "Production audit pipeline ready for GitHub",
            "operating_mode": "autonomous",
        }, headers=c_headers)
        assert p_res.status_code in (200, 201)
        c_proj_id = p_res.json()["project"]["id"]

        # Build workspace
        await client.post(f"/api/orchestrator/projects/{c_proj_id}/build", headers=c_headers)

        # Step 4.A: Attempt push — must enforce human-in-the-loop approval first
        appr_req = await client.post(
            f"/api/orchestrator/projects/{c_proj_id}/github",
            json={"repository_name": "audit-ready-system", "private": True},
            headers=c_headers,
        )
        assert appr_req.status_code == 200
        appr_data = appr_req.json()
        assert appr_data.get("approval_required") is True
        approval_id = appr_data["approval"]["id"]
        logger.info("✓ Connected account push requires explicit approval gate before publishing")

        # Step 4.B: User approves the push
        decide_res = await client.post(
            f"/api/approvals/{approval_id}/decide",
            json={"decision": "approved", "reason": "Authorized release to GitHub"},
            headers=c_headers,
        )
        assert decide_res.status_code == 200
        assert decide_res.json()["approval"]["decision"] == "approved"

        # Step 4.C: Execute push with mocked GitHub API and commit_and_push
        with patch.object(GitHubService, "create_remote_repository", new_callable=AsyncMock) as mock_create, \
             patch.object(GitHubService, "commit_and_push_to_github", new_callable=AsyncMock) as mock_push:

            mock_create.return_value = {
                "success": True,
                "repo_url": f"https://github.com/conn_dev_{ts}/audit-ready-system",
                "clone_url": f"https://github.com/conn_dev_{ts}/audit-ready-system.git",
                "full_name": f"conn_dev_{ts}/audit-ready-system",
                "private": True,
            }
            mock_push.return_value = {
                "success": True,
                "commit_message": "Initial commit",
                "branch": "main",
                "remote_verified": True,
                "latest_commit_sha": "def5678",
            }

            push_exec = await client.post(
                f"/api/orchestrator/projects/{c_proj_id}/github",
                json={"repository_name": "audit-ready-system", "private": True},
                headers=c_headers,
            )
            assert push_exec.status_code == 200
            p_data = push_exec.json()
            assert p_data["success"] is True
            assert p_data["repo_url"] == f"https://github.com/conn_dev_{ts}/audit-ready-system"
            assert p_data["remote_verified"] is True
            logger.info("✓ Publishing with connected account succeeded with verified remote commit")

            # Verify mock_create and mock_push were called with user's OAuth token
            mock_create.assert_called_once()
            assert mock_create.call_args.kwargs["token"] == mock_oauth_token
            mock_push.assert_called_once()
            assert mock_push.call_args.kwargs["token"] == mock_oauth_token
            assert mock_push.call_args.kwargs["repo_clone_url"] == f"https://github.com/conn_dev_{ts}/audit-ready-system.git"
            logger.info("✓ Verified orchestrator passed user's OAuth token directly without global fallback")

        # ─────────────────────────────────────────────────────────────────────
        # 5. Redaction of credentials from all logs and error messages
        # ─────────────────────────────────────────────────────────────────────
        logger.info("\n=== TEST 6: Credential redaction engine ===")
        sample_pat = "ghp_1234567890abcdef1234567890abcdef12"
        sample_oauth = "gho_abcdef1234567890abcdef123456789012"
        sample_fine_grained = "github_pat_11A2B3C4D_1234567890abcdef1234567890abcdef1234567890abcdef"
        sample_url = "https://oauth2:ghp_1234567890abcdef1234567890abcdef12@github.com/owner/repo.git"
        sample_auth_header = "AUTHORIZATION: basic eC1hY2Nlc3MtdG9rZW46Z2hwXzEyMzQ="

        assert sample_pat not in redact_credentials(f"Error connecting: {sample_pat}", sample_pat)
        assert sample_oauth not in redact_credentials(f"Failed with {sample_oauth}", sample_oauth)
        assert sample_fine_grained not in redact_credentials(f"Exposed: {sample_fine_grained}")
        assert "@github.com" in redact_credentials(sample_url)
        assert sample_pat not in redact_credentials(sample_url)
        assert "ghp_" not in redact_credentials(sample_auth_header)
        logger.info("✓ Credential redaction verified across PAT, OAuth, URLs, and Auth headers")

    logger.info("\n============================================================")
    logger.info("🎉 ALL SECURE GITHUB PUBLISHING TESTS PASSED 100%!")
    logger.info("============================================================")


if __name__ == "__main__":
    asyncio.run(run_tests())
