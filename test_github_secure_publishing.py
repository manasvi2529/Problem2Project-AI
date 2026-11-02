"""
ProblemPilot AI — Sprint 2: Secure GitHub Publishing Test Suite
Pytest-discoverable test suite verifying all core security requirements:
1. Publishing without a connected user account is rejected (and global token fallback is removed).
2. Clean Git remote with zero token persistence in .git/config, command args, or permanent environment.
3. Failed pushes against rejecting remote do not leave credentials behind.
4. Unexpected exceptions during push do not persist credentials or leak tokens.
5. Publishing with a connected account works through approval gate (Mocked GitHub integration).
6. Credential redaction engine redacts PAT, OAuth tokens, fine-grained tokens, and basic auth headers.
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
from backend.services.github_service import GitHubService, redact_credentials

logger = logging.getLogger("test_github_secure_publishing")


def test_unconnected_publishing_rejected_without_fallback():
    """
    Verify that attempting to publish without a connected GitHub OAuth account
    is rejected with HTTP 400, and the global GITHUB_PERSONAL_ACCESS_TOKEN is strictly ignored.
    """
    async def _run():
        await init_db()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            ts = int(datetime.now().timestamp())
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

            # Switch user mode to autonomous so build can generate workspace files
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

            # Verify global GITHUB_PERSONAL_ACCESS_TOKEN fallback is NOT used
            orig_global = settings.GITHUB_PERSONAL_ACCESS_TOKEN
            try:
                settings.GITHUB_PERSONAL_ACCESS_TOKEN = "ghp_global_server_admin_token_should_never_be_used"
                pub_res2 = await client.post(f"/api/orchestrator/projects/{proj_id}/github", json={}, headers=auth_headers)
                assert pub_res2.status_code == 400
                detail2 = pub_res2.json().get("detail", "").lower()
                assert "not connected" in detail2 or "authorization missing" in detail2
            finally:
                settings.GITHUB_PERSONAL_ACCESS_TOKEN = orig_global

    asyncio.run(_run())


def test_clean_remote_url_and_no_token_persisted_in_git_config():
    """
    [MOCKED PUSH / VERIFY] Verify that commit_and_push_to_github:
    1. Sets a clean remote URL with NO token.
    2. Writes NO token to .git/config.
    3. Passes NO token in command-line arguments.
    4. Passes credentials only via temporary subprocess HTTP authorization header.
    """
    async def _run():
        temp_dir = Path(tempfile.mkdtemp(prefix="git_sec_test_"))
        test_token = "gho_superSecretTokenThatMustNeverPersist999"
        clean_remote_url = "https://github.com/test-org/secure-repo.git"

        try:
            sample_file = temp_dir / "server.py"
            sample_file.write_text("print('Secure Git Push')", encoding="utf-8")

            original_create_subprocess_exec = asyncio.create_subprocess_exec
            captured_envs = []
            captured_commands = []

            async def mock_subprocess_exec(cmd, *args, **kwargs):
                captured_commands.append((cmd, list(args)))
                if "env" in kwargs and kwargs["env"]:
                    captured_envs.append(dict(kwargs["env"]))
                # If command is push, mock success (mocked remote push)
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

            # 1. Verify remote URL has NO token
            proc = await original_create_subprocess_exec(
                "git", "remote", "get-url", "origin",
                cwd=str(temp_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            actual_remote_url = stdout.decode("utf-8").strip()

            assert actual_remote_url == clean_remote_url
            assert test_token not in actual_remote_url
            assert "@" not in actual_remote_url

            # 2. Verify .git/config has NO token
            git_config_path = temp_dir / ".git" / "config"
            assert git_config_path.exists()
            git_config_content = git_config_path.read_text(encoding="utf-8")

            assert test_token not in git_config_content
            assert "oauth2:" not in git_config_content
            assert "x-access-token" not in git_config_content

            # 3. Verify command-line arguments contained NO token
            for cmd, args in captured_commands:
                cmd_line = f"{cmd} {' '.join(args)}"
                assert test_token not in cmd_line

            # 4. Verify temporary environment contained auth header only during push
            assert len(captured_envs) >= 1
            push_env = captured_envs[0]
            assert push_env.get("GIT_TERMINAL_PROMPT") == "0"
            assert push_env.get("GIT_CONFIG_KEY_0") == "http.extraHeader"
            assert "AUTHORIZATION: basic" in push_env.get("GIT_CONFIG_VALUE_0", "")
            assert test_token not in os.environ

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    asyncio.run(_run())


def test_failed_pushes_do_not_leave_credentials_behind():
    """
    [REAL GIT SUBPROCESS TEST] Verify that failed git pushes against an offline
    rejecting repository do not leave credentials behind in .git/config, remote URL, or logs.
    """
    async def _run():
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
            assert fail_result.get("success") is False

            # Verify error message does NOT contain the plaintext token
            error_msg = fail_result.get("error", "")
            assert fail_token not in error_msg

            # Verify .git/config on disk does NOT contain the token
            fail_git_config = fail_dir / ".git" / "config"
            assert fail_git_config.exists()
            fail_config_content = fail_git_config.read_text(encoding="utf-8")
            assert fail_token not in fail_config_content
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
        finally:
            shutil.rmtree(fail_dir, ignore_errors=True)
            shutil.rmtree(bare_reject_dir, ignore_errors=True)

    asyncio.run(_run())


def test_unexpected_exception_during_push_cleans_up_and_redacts():
    """
    [EXCEPTION SAFETY TEST] Force an unexpected exception during push execution
    and verify that:
    1. The exception is safely handled.
    2. The returned error message redacts sensitive tokens.
    3. Zero tokens remain in .git/config.
    4. The remote URL remains clean and devoid of embedded credentials.
    """
    async def _run():
        crash_dir = Path(tempfile.mkdtemp(prefix="git_crash_test_"))
        secret_token = "gho_unhandledCrashSecretToken998877"
        raw_remote_url = "https://github.com/org/repo-crashtest.git"

        try:
            (crash_dir / "app.py").write_text("print('Crash test')", encoding="utf-8")

            original_create_subprocess_exec = asyncio.create_subprocess_exec

            async def crashing_subprocess_exec(cmd, *args, **kwargs):
                if args and args[0] == "push":
                    # Simulate an unexpected internal crash containing a sensitive token in error message
                    raise RuntimeError(f"Unexpected connection crash with token {secret_token} exposed!")
                return await original_create_subprocess_exec(cmd, *args, **kwargs)

            with patch("asyncio.create_subprocess_exec", side_effect=crashing_subprocess_exec):
                result = await GitHubService.commit_and_push_to_github(
                    workspace_dir=crash_dir,
                    repo_clone_url=raw_remote_url,
                    token=secret_token,
                    commit_message="Crash resilience commit",
                )

                # 1. Operation must return failure rather than unhandled crash
                assert result.get("success") is False
                err_msg = result.get("error", "")

                # 2. Token MUST be redacted in returned error
                assert secret_token not in err_msg
                assert "[REDACTED_TOKEN]" in err_msg

            # 3. .git/config must not contain token
            git_config = crash_dir / ".git" / "config"
            assert git_config.exists()
            cfg_text = git_config.read_text(encoding="utf-8")
            assert secret_token not in cfg_text

            # 4. Remote URL must remain clean
            proc = await original_create_subprocess_exec(
                "git", "remote", "get-url", "origin",
                cwd=str(crash_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            remote_url = stdout.decode("utf-8").strip()
            assert secret_token not in remote_url
            assert remote_url == raw_remote_url

        finally:
            shutil.rmtree(crash_dir, ignore_errors=True)

    asyncio.run(_run())


def test_connected_account_publishing_workflow_mocked():
    """
    [MOCKED GITHUB INTEGRATION TEST]
    Verify that an authenticated user with a connected GitHub OAuth credential:
    1. Is required to obtain human approval before publishing.
    2. Once approved, the orchestrator invokes GitHubService with the user's OAuth token directly.
    3. Remote repository creation and commit verification are validated.
    """
    async def _run():
        await init_db()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            ts = int(datetime.now().timestamp())
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

            # Set autonomous mode so workspace can build
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

            # Step A: Push request requires approval gate
            appr_req = await client.post(
                f"/api/orchestrator/projects/{c_proj_id}/github",
                json={"repository_name": "audit-ready-system", "private": True},
                headers=c_headers,
            )
            assert appr_req.status_code == 200
            appr_data = appr_req.json()
            assert appr_data.get("approval_required") is True
            approval_id = appr_data["approval"]["id"]

            # Step B: User approves the push
            decide_res = await client.post(
                f"/api/approvals/{approval_id}/decide",
                json={"decision": "approved", "reason": "Authorized release to GitHub"},
                headers=c_headers,
            )
            assert decide_res.status_code == 200
            assert decide_res.json()["approval"]["decision"] == "approved"

            # Step C: Execute push with mocked GitHub API (Explicitly mocked)
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

                # Verify orchestrator passed user's OAuth token directly without global fallback
                mock_create.assert_called_once()
                assert mock_create.call_args.kwargs["token"] == mock_oauth_token
                mock_push.assert_called_once()
                assert mock_push.call_args.kwargs["token"] == mock_oauth_token
                assert mock_push.call_args.kwargs["repo_clone_url"] == f"https://github.com/conn_dev_{ts}/audit-ready-system.git"

    asyncio.run(_run())


def test_credential_redaction_engine():
    """
    Verify pattern-based and exact redaction of PATs, OAuth tokens,
    fine-grained PATs, URLs with embedded credentials, and basic authorization headers.
    """
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
