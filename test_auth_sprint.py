"""
Problem2Project AI — Stabilization Sprint 1: Authentication Only Test Suite

Exhaustively verifies:
1. Python compilation (verified by runner).
2. Frontend JavaScript syntax (verified by node --check).
3. User registration test (success, duplicate email, duplicate username, invalid email format).
4. Valid login test (returns JWT token and sanitized user profile).
5. Invalid login test (wrong password, non-existent user, old hardcoded developer credentials).
6. Session persistence test (GET /api/auth/me with valid Bearer token, settings persistence).
7. Logout test (unauthenticated requests rejected with 401).
8. Expired session test (expired JWT rejected with 401).
9. Database integrity check (database initialization preserves legitimate users).
"""
import sys
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.database import init_db, AsyncSessionLocal
from backend.models.user import User
from backend.security import create_access_token
from sqlalchemy import select

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_auth_sprint")


async def run_auth_sprint_tests():
    logger.info("Initializing Database for Authentication Sprint 1...")
    await init_db()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        # ── Test 3: User Registration Test ───────────────────────────────────
        logger.info("\n=== Running Test 3: User Registration Test ===")
        ts = int(datetime.now().timestamp())
        valid_email = f"alice_{ts}@domain.io"
        valid_username = f"alice_{ts}"
        valid_password = "SuperSecretPassword123!"

        reg_payload = {
            "name": "Alice Cooper",
            "username": valid_username,
            "email": valid_email,
            "password": valid_password,
        }
        reg_res = await client.post("/api/auth/register", json=reg_payload)
        assert reg_res.status_code == 201, f"Registration failed: {reg_res.text}"
        reg_data = reg_res.json()
        assert "access_token" in reg_data and "token" in reg_data, "Missing JWT token alias"
        user_info = reg_data["user"]
        assert user_info["email"] == valid_email
        assert user_info["username"] == valid_username
        assert "hashed_password" not in user_info, "Security violation: hashed_password exposed in response"
        assert "password" not in user_info, "Security violation: password exposed in response"
        logger.info("✓ Valid user registration succeeded with 201 Created and secure token generation")

        # Duplicate email test
        dup_email_res = await client.post("/api/auth/register", json={
            "name": "Alice Clone",
            "username": f"unique_user_{ts}",
            "email": valid_email,
            "password": "Password456!",
        })
        assert dup_email_res.status_code == 409, f"Expected 409 Conflict, got {dup_email_res.status_code}"
        logger.info("✓ Duplicate email registration rejected with 409 Conflict")

        # Duplicate username test
        dup_user_res = await client.post("/api/auth/register", json={
            "name": "Alice Another",
            "username": valid_username,
            "email": f"different_{ts}@domain.io",
            "password": "Password456!",
        })
        assert dup_user_res.status_code == 409, f"Expected 409 Conflict, got {dup_user_res.status_code}"
        logger.info("✓ Duplicate username registration rejected with 409 Conflict")

        # Invalid email format test
        invalid_email_res = await client.post("/api/auth/register", json={
            "name": "Invalid Email",
            "username": f"bad_email_{ts}",
            "email": "not-an-email",
            "password": "Password456!",
        })
        assert invalid_email_res.status_code == 400, f"Expected 400 Bad Request, got {invalid_email_res.status_code}"
        logger.info("✓ Invalid email format rejected with 400 Bad Request")

        # ── Test 4: Valid Login Test ─────────────────────────────────────────
        logger.info("\n=== Running Test 4: Valid Login Test ===")
        login_res = await client.post("/api/auth/login", json={
            "email": valid_email,
            "password": valid_password,
        })
        assert login_res.status_code == 200, f"Valid login failed: {login_res.text}"
        login_data = login_res.json()
        assert "access_token" in login_data and "token" in login_data
        assert login_data["user"]["email"] == valid_email
        assert "hashed_password" not in login_data["user"]
        active_token = login_data["access_token"]
        logger.info("✓ Valid login succeeded with 200 OK and valid JWT token")

        # ── Test 5: Invalid Login Test ───────────────────────────────────────
        logger.info("\n=== Running Test 5: Invalid Login Test ===")
        # Wrong password
        wrong_pwd_res = await client.post("/api/auth/login", json={
            "email": valid_email,
            "password": "IncorrectPassword999!",
        })
        assert wrong_pwd_res.status_code == 401, f"Expected 401, got {wrong_pwd_res.status_code}"
        logger.info("✓ Login with incorrect password rejected with 401 Unauthorized")

        # Non-existent user
        non_existent_res = await client.post("/api/auth/login", json={
            "email": "ghost_user_99999@nowhere.com",
            "password": "Password123!",
        })
        assert non_existent_res.status_code == 401, f"Expected 401, got {non_existent_res.status_code}"
        logger.info("✓ Login with non-existent user rejected with 401 Unauthorized")

        # Old hardcoded developer credentials
        backdoor_res = await client.post("/api/auth/login", json={
            "email": "developer@problempilot.ai",
            "password": "ProblemPilot123!",
        })
        assert backdoor_res.status_code == 401, f"Expected 401, got {backdoor_res.status_code}"
        logger.info("✓ Login with old hardcoded developer credentials rejected with 401 Unauthorized")

        # ── Test 6: Session Persistence Test ─────────────────────────────────
        logger.info("\n=== Running Test 6: Session Persistence Test ===")
        auth_headers = {"Authorization": f"Bearer {active_token}"}
        me_res = await client.get("/api/auth/me", headers=auth_headers)
        assert me_res.status_code == 200, f"Session verification failed: {me_res.text}"
        me_data = me_res.json()
        assert me_data["user"]["email"] == valid_email
        assert me_data["user"]["username"] == valid_username
        logger.info("✓ Session persistence verified via GET /api/auth/me")

        # Mode switching persistence
        mode_res = await client.put("/api/auth/mode", json={"mode": "autonomous"}, headers=auth_headers)
        assert mode_res.status_code == 200
        assert mode_res.json()["operating_mode"] == "autonomous"

        me_res2 = await client.get("/api/auth/me", headers=auth_headers)
        assert me_res2.json()["user"]["operating_mode"] == "autonomous"
        logger.info("✓ User preferences and operating mode persisted in database")

        # ── Test 7: Logout / Unauthenticated Test ─────────────────────────────
        logger.info("\n=== Running Test 7: Logout / Unauthenticated Request Test ===")
        # Without Authorization header
        unauth_res = await client.get("/api/auth/me")
        assert unauth_res.status_code == 401, f"Expected 401, got {unauth_res.status_code}"
        logger.info("✓ Request without token properly rejected with 401 Unauthorized")

        # With empty bearer token
        empty_auth_res = await client.get("/api/auth/me", headers={"Authorization": "Bearer "})
        assert empty_auth_res.status_code == 401, f"Expected 401, got {empty_auth_res.status_code}"
        logger.info("✓ Request with empty Bearer header properly rejected with 401 Unauthorized")

        # ── Test 8: Expired Session Test ─────────────────────────────────────
        logger.info("\n=== Running Test 8: Expired Session Test ===")
        expired_token = create_access_token(
            data={"sub": user_info["id"]},
            expires_delta=timedelta(seconds=-3600),  # Expired 1 hour ago
        )
        expired_res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
        assert expired_res.status_code == 401, f"Expected 401, got {expired_res.status_code}"
        assert "expired" in expired_res.json()["detail"].lower() or "invalid" in expired_res.json()["detail"].lower()
        logger.info("✓ Expired JWT session correctly rejected with 401 Unauthorized ('Invalid or expired token')")

        # ── Test 9: Database Integrity Check ─────────────────────────────────
        logger.info("\n=== Running Test 9: Database Integrity Check ===")
        # Ensure that running init_db() does not delete the legitimate user we just registered
        await init_db()
        async with AsyncSessionLocal() as session:
            check_user = await session.execute(select(User).where(User.email == valid_email))
            user_found = check_user.scalar_one_or_none()
            assert user_found is not None, "FATAL: Database initialization deleted legitimate registered user!"
            assert user_found.id == user_info["id"]
            logger.info("✓ Database initialization preserved legitimate registered user successfully")

    logger.info("\n" + "=" * 60)
    logger.info("🎉 ALL AUTHENTICATION TESTS (REGISTRATION, LOGIN, INVALID LOGIN, PERSISTENCE, LOGOUT, EXPIRATION, DB INTEGRITY) PASSED 100%!")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_auth_sprint_tests())

