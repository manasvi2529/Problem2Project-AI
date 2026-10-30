"""
ProblemPilot AI — Complete GitHub OAuth + Vercel Deployment Integration Test Suite
Validates all OAuth flows, token encryption, secret scanning, repository creation,
Vercel API validation, deployment lifecycles, approval gates, and deployment history.
"""
import os
import sys
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock, MagicMock
import httpx
from httpx import AsyncClient, ASGITransport

# Set test environment
os.environ["APP_ENV"] = "testing"
os.environ["DEBUG"] = "true"

from backend.main import app
from backend.config import settings
from backend.database import init_db, AsyncSessionLocal
from backend.models.user import User
from backend.models.project import Project
from backend.models.deployment import Deployment
from backend.models.approval import Approval
from backend.services.github_service import GitHubService
from backend.services.cloud_deployer import CloudDeployer
from backend.services.approval_engine import ApprovalEngine
from backend.security import (
    encrypt_credential,
    decrypt_credential,
    generate_oauth_state,
    verify_oauth_state,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_integrations")


async def run_all_integration_tests():
    logger.info("Initializing Database for Integration Verification...")
    await init_db()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register a test developer user
        ts = int(datetime.now().timestamp())
        reg_res = await client.post("/api/auth/register", json={
            "name": "Integration Tester",
            "username": f"integ_{ts}",
            "email": f"integ_{ts}@example.com",
            "password": "Password123!",
        })
        assert reg_res.status_code == 201, f"Registration failed: {reg_res.text}"
        auth_data = reg_res.json()
        token = auth_data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        user_id = auth_data["user"]["id"]

        logger.info("\n============================================================")
        logger.info("1. TESTING CREDENTIAL ENCRYPTION & TAMPER-PROOF CSRF TOKENS")
        logger.info("============================================================")

        # 1.1 Token encryption at rest
        raw_token = "gho_1234567890abcdef1234567890abcdef12"
        cipher = encrypt_credential(raw_token)
        assert cipher.startswith("enc:v1:"), f"Ciphertext must start with enc:v1:, got {cipher}"
        assert raw_token not in cipher, "Plaintext token must never appear in ciphertext"

        decrypted = decrypt_credential(cipher)
        assert decrypted == raw_token, f"Decrypted token mismatch: {decrypted} != {raw_token}"
        logger.info("✓ AES-256 / Fernet token encryption and decryption at rest verified")

        # 1.2 Tamper-proof HMAC CSRF state
        state = generate_oauth_state(user_id)
        assert len(state.split(":")) == 4, "State token must contain user_id, timestamp, nonce, and signature"
        extracted_uid = verify_oauth_state(state)
        assert extracted_uid == user_id, f"State verification failed: {extracted_uid} != {user_id}"

        # Tampered state rejection
        tampered_state = state[:-4] + "ffff"
        assert verify_oauth_state(tampered_state) is None, "Tampered state signature must be rejected"

        # Expired state rejection
        expired_payload = f"{user_id}:{int(datetime.now(timezone.utc).timestamp()) - 1000}:nonce"
        import hmac, hashlib
        sig = hmac.new((settings.GITHUB_OAUTH_STATE_SECRET or settings.SECRET_KEY).encode("utf-8"), expired_payload.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
        expired_state = f"{expired_payload}:{sig}"
        assert verify_oauth_state(expired_state, max_age_seconds=600) is None, "Expired state must be rejected"
        logger.info("✓ Cryptographic HMAC CSRF state generation and tamper protection verified")

        logger.info("\n============================================================")
        logger.info("2. TESTING GITHUB OAUTH LIFECYCLE (STARTUP, CALLBACK, DISCONNECT)")
        logger.info("============================================================")

        # 2.1 Missing OAuth Configuration Detection
        orig_id = settings.GITHUB_CLIENT_ID
        settings.GITHUB_CLIENT_ID = None
        auth_err_res = await client.get("/api/integrations/github/authorize", headers=headers)
        assert auth_err_res.status_code == 503, "Must return 503 when GITHUB_CLIENT_ID is missing"
        assert "GITHUB_CLIENT_ID" in auth_err_res.json()["detail"]
        logger.info("✓ Missing OAuth configuration gracefully detected with explicit variable names")

        # Restore configuration for tests
        settings.GITHUB_CLIENT_ID = "test_client_id_123"
        settings.GITHUB_CLIENT_SECRET = "test_client_secret_456"

        # 2.2 Authorize URL Generation
        auth_res = await client.get("/api/integrations/github/authorize", headers=headers)
        assert auth_res.status_code == 200
        auth_data_resp = auth_res.json()
        assert "auth_url" in auth_data_resp
        assert "github.com/login/oauth/authorize" in auth_data_resp["auth_url"]
        assert f"client_id={settings.GITHUB_CLIENT_ID}" in auth_data_resp["auth_url"]
        assert settings.GITHUB_REDIRECT_URI in auth_data_resp["auth_url"]
        created_state = auth_data_resp["state"]
        logger.info(f"✓ GitHub OAuth authorization URL generated with callback: {settings.GITHUB_REDIRECT_URI}")

        # 2.3 Successful OAuth Callback (Mocked Exchange & User API)
        with patch.object(GitHubService, "exchange_code_for_token", new_callable=AsyncMock) as mock_exchange:
            mock_exchange.return_value = {
                "success": True,
                "access_token": "gho_mock_access_token_999",
                "token_type": "bearer",
                "scope": "repo,read:user",
                "user": {
                    "username": "octocat-tester",
                    "name": "Octo Cat",
                    "email": "octocat@github.test",
                    "public_repos": 14,
                },
            }
            cb_res = await client.get(
                f"/api/integrations/github/callback?code=mock_auth_code_789&state={created_state}",
                follow_redirects=False,
            )
            assert cb_res.status_code in (302, 307), f"Expected redirect after callback, got {cb_res.status_code}"
            assert "github_connected=true" in cb_res.headers.get("location", "")
            logger.info("✓ OAuth callback exchanged authorization code for token and redirected cleanly")

        # 2.4 Test Connection & Token Decryption
        with patch.object(GitHubService, "verify_github_token", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = {
                "valid": True,
                "username": "octocat-tester",
                "name": "Octo Cat",
                "email": "octocat@github.test",
                "public_repos": 14,
                "scopes": "repo, read:user",
            }
            test_conn_res = await client.get("/api/integrations/github/test", headers=headers)
            assert test_conn_res.status_code == 200
            tc_data = test_conn_res.json()
            assert tc_data["connected"] is True
            assert tc_data["username"] == "octocat-tester"
            assert tc_data["public_repos"] == 14
            assert "token" not in tc_data, "Token must NEVER be exposed in test connection response"
            logger.info("✓ GET /api/integrations/github/test verified account connection without exposing token")

        # Verify token in DB is encrypted at rest
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select
            db_user = (await session.execute(select(User).where(User.id == user_id))).scalar_one()
            assert db_user.github_access_token.startswith("enc:v1:"), "Token in DB must be encrypted at rest"
            assert db_user.get_github_token() == "gho_mock_access_token_999"
            logger.info("✓ Confirmed DB user record holds encrypted ciphertext at rest")

        # 2.5 Disconnect GitHub
        disc_res = await client.delete("/api/integrations/github", headers=headers)
        assert disc_res.status_code == 200
        disc_test_res = await client.get("/api/integrations/github/test", headers=headers)
        assert disc_test_res.json()["connected"] is False
        logger.info("✓ DELETE /api/integrations/github safely cleared credentials and revoked state")

        logger.info("\n============================================================")
        logger.info("3. TESTING PRE-PUSH SECURITY SCANNING & GIT SAFETY")
        logger.info("============================================================")

        # 3.1 Pre-push secret scanning
        clean_files = {
            "server.py": "from fastapi import FastAPI\napp = FastAPI()",
            "index.html": "<!DOCTYPE html><html><body><h1>App</h1></body></html>",
        }
        assert len(GitHubService.scan_files_for_secrets(clean_files)) == 0

        dirty_files = {
            "config.py": "OPENAI_KEY = 'sk-abcdef1234567890abcdef1234567890abcdef'",
            ".env": "SECRET_KEY=supersecretkey",
            "rsa.pem": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0...",
        }
        findings = GitHubService.scan_files_for_secrets(dirty_files)
        assert len(findings) == 3, f"Expected 3 exposed secrets, caught {len(findings)}"
        types = [f["type"] for f in findings]
        assert "Sensitive Environment/Key File" in types
        assert "OpenAI / Claude Secret Key" in types
        assert "Private Cryptographic Key" in types
        logger.info(f"✓ Pre-push security scanner detected {len(findings)} sensitive files & credential patterns")

        logger.info("\n============================================================")
        logger.info("4. TESTING VERCEL CONNECTION VALIDATION & STRUCTURE INSPECTOR")
        logger.info("============================================================")

        # 4.1 Unconfigured Vercel Token Check
        orig_vercel_token = settings.VERCEL_TOKEN
        settings.VERCEL_TOKEN = None
        v_check = await CloudDeployer.verify_vercel_token()
        assert v_check["verified"] is False
        assert v_check["status"] == "not_configured"
        logger.info("✓ Vercel unconfigured status verified")

        # 4.2 Valid Token Verification (Mocked Vercel /v2/user API)
        mock_vercel_user = MagicMock()
        mock_vercel_user.status_code = 200
        mock_vercel_user.json.return_value = {
            "user": {
                "id": "usr_vercel_12345",
                "username": "vercel-dev",
                "email": "dev@vercel.test",
                "name": "Vercel Developer",
            }
        }
        with patch("httpx.AsyncClient.get", return_value=mock_vercel_user):
            v_conn = await CloudDeployer.verify_vercel_token(token="vck_mock_valid_token")
            assert v_conn["verified"] is True
            assert v_conn["status"] == "connected"
            assert v_conn["username"] == "vercel-dev"
            logger.info("✓ Vercel API token verification passed with authenticated user info")

        # 4.3 Permission Denied Token Check (HTTP 403)
        mock_v_denied = MagicMock()
        mock_v_denied.status_code = 403
        mock_v_denied.text = "Forbidden: Insufficient permissions"
        with patch("httpx.AsyncClient.get", return_value=mock_v_denied):
            v_denied = await CloudDeployer.verify_vercel_token(token="vck_restricted_token")
            assert v_denied["verified"] is False
            assert v_denied["status"] == "permission_denied"
            logger.info("✓ Vercel permission denied (403) handling verified")

        # 4.4 Project Structure Inspector
        workspace_dir = settings.DATA_DIR / "sandboxes" / "sample_inspection_test"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        (workspace_dir / "server.py").write_text("from fastapi import FastAPI\napp = FastAPI()", encoding="utf-8")
        (workspace_dir / "index.html").write_text("<!DOCTYPE html><html><body>Test</body></html>", encoding="utf-8")
        (workspace_dir / "requirements.txt").write_text("fastapi\nuvicorn", encoding="utf-8")

        structure = CloudDeployer.validate_project_structure(workspace_dir)
        assert structure["project_type"] == "hybrid_python_static"
        assert structure["compatible_vercel"] is True
        assert structure["has_backend"] is True
        assert structure["has_frontend"] is True
        logger.info("✓ Project structure inspection verified hybrid Python FastAPI + HTML5 static frontend")

        logger.info("\n============================================================")
        logger.info("5. TESTING VERCEL DEPLOYMENT SUBMISSION, POLLING & HEALTH CHECK")
        logger.info("============================================================")

        # Mock Vercel Deployment Creation (HTTP 200)
        mock_dep_create = MagicMock()
        mock_dep_create.status_code = 200
        mock_dep_create.json.return_value = {
            "id": "dpl_vercel_mock_999",
            "url": "problempilot-app.vercel.app",
            "readyState": "READY",
        }

        # Mock Health Check (HTTP 200)
        mock_health_resp = MagicMock()
        mock_health_resp.status_code = 200
        mock_health_resp.json.return_value = {"status": "healthy", "service": "ProblemPilot Live Service"}
        mock_health_resp.elapsed = MagicMock()
        mock_health_resp.elapsed.total_seconds.return_value = 0.045

        async def mock_deploy_dispatch(url, *args, **kwargs):
            if "deployments" in str(url):
                return mock_dep_create
            return mock_health_resp

        with patch("httpx.AsyncClient.post", side_effect=mock_deploy_dispatch), \
             patch("httpx.AsyncClient.get", side_effect=mock_deploy_dispatch):
            deploy_result = await CloudDeployer.execute_cloud_deployment(
                workspace_dir=workspace_dir,
                project_name="Sample Sentinel",
                provider="vercel",
                provider_token="vck_mock_valid_token",
            )
            assert deploy_result["success"] is True
            assert deploy_result["provider"] == "vercel"
            assert deploy_result["deployment_id"] == "dpl_vercel_mock_999"
            assert "https://problempilot-app.vercel.app" in deploy_result["deploy_url"]
            assert deploy_result["ready_state"] == "READY"
            assert deploy_result["health_check"]["verified"] is True
            logger.info(f"✓ Vercel deployment submitted, verified ready, and health-probed: {deploy_result['deploy_url']}")

        logger.info("\n============================================================")
        logger.info("6. TESTING END-TO-END ORCHESTRATOR APPROVAL & DEPLOYMENT PERSISTENCE")
        logger.info("============================================================")

        # Create a test project in DB
        proj_res = await client.post("/api/projects", json={
            "name": "Cloud Deployment Project",
            "description": "Autonomous cloud deployment verification test",
            "repository_name": "cloud-deploy-proj",
        }, headers=headers)
        assert proj_res.status_code == 200
        proj_id = proj_res.json()["project"]["id"]

        # Step 1: Deploy cloud without approval -> MUST halt and require approval
        halt_res = await client.post(f"/api/orchestrator/projects/{proj_id}/deploy", json={"provider": "vercel"}, headers=headers)
        assert halt_res.status_code == 200
        halt_data = halt_res.json()
        assert halt_data.get("approval_required") is True
        assert "vercel.json" in halt_data.get("manifests_generated", [])
        appr_id = halt_data["approval"]["id"]
        logger.info("✓ Backend-enforced approval gate successfully halted unapproved cloud deployment")

        # Step 2: Approve the deployment
        dec_res = await client.post(f"/api/approvals/{appr_id}/decide", json={"decision": "approved"}, headers=headers)
        assert dec_res.status_code == 200
        logger.info("✓ Consequential deployment approval granted by user")

        # Step 3: Execute deployment with mock provider
        settings.VERCEL_TOKEN = "vck_mock_token_active"
        with patch.object(CloudDeployer, "execute_cloud_deployment", new_callable=AsyncMock) as mock_exec_dep:
            mock_exec_dep.return_value = {
                "success": True,
                "provider": "vercel",
                "configured": True,
                "deployment_id": "dpl_vercel_mock_999",
                "deploy_url": "https://problempilot-app.vercel.app",
                "ready_state": "READY",
                "manifests_generated": ["vercel.json", "Dockerfile"],
                "health_check": {"verified": True},
                "message": "Successfully deployed to Vercel",
            }
            exec_res = await client.post(f"/api/orchestrator/projects/{proj_id}/deploy", json={"provider": "vercel"}, headers=headers)
            assert exec_res.status_code == 200
            exec_data = exec_res.json()
            assert exec_data["success"] is True
            assert exec_data["deployment_id"] == "dpl_vercel_mock_999"
            logger.info("✓ Approved cloud deployment executed, consumed approval, and deployed to Vercel")

        # Step 4: Verify approval is now consumed (replay attack prevention)
        async with AsyncSessionLocal() as session:
            is_valid_again = await ApprovalEngine.verify_approved(
                db=session,
                user_id=user_id,
                action_type="deploy_cloud",
                project_id=proj_id,
                action_params={"provider": "vercel"},
            )
            assert is_valid_again is None, "Consumed approval must NEVER be reusable"
            logger.info("✓ Single-use approval consumption confirmed: replay attack blocked")

        # Step 5: Check deployment history API
        hist_res = await client.get("/api/integrations/deployments", headers=headers)
        assert hist_res.status_code == 200
        hist_data = hist_res.json()
        assert len(hist_data["deployments"]) >= 1
        latest_dep = hist_data["deployments"][0]
        assert latest_dep["project_id"] == proj_id
        assert latest_dep["provider"] == "vercel"
        assert latest_dep["status"] == "ready"
        assert latest_dep["deployment_id"] == "dpl_vercel_mock_999"
        logger.info(f"✓ GET /api/integrations/deployments returned persistent audit history for deployment {latest_dep['id']}")

        # Step 6: Verify overall integrations status API
        overall_res = await client.get("/api/integrations/status", headers=headers)
        assert overall_res.status_code == 200
        st_data = overall_res.json()
        assert st_data["callback_url"] == settings.GITHUB_REDIRECT_URI
        assert "vercel" in st_data["cloud"]
        logger.info("✓ GET /api/integrations/status verified with single-source-of-truth callback URL")

        # Clean up temporary test workspace
        try:
            import shutil
            shutil.rmtree(workspace_dir, ignore_errors=True)
        except Exception:
            pass

    logger.info("\n============================================================")
    logger.info("🎉 ALL GITHUB OAUTH & VERCEL DEPLOYMENT INTEGRATION TESTS PASSED 100%!")
    logger.info("============================================================")


if __name__ == "__main__":
    asyncio.run(run_all_integration_tests())

