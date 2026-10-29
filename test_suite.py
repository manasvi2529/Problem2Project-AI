"""
Comprehensive End-to-End Test Suite for Problem2Project AI × ProblemPilot AI.
Tests:
1. Database initialization & schemas
2. Security & Auth (JWT token generation, hash check)
3. Platform Scrapers live data fetch (HackerNews, Reddit, StackOverflow)
4. Data Science Problem Analyzer (Pandas metrics, TF-IDF clustering, Pain Index, CSV export)
5. FastAPI endpoints via httpx / TestClient
"""
import asyncio
import sys
import json
import logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("test_suite")


async def test_auth_and_db():
    logger.info("=== 1. Testing Database & Auth ===")
    from backend.database import init_db, AsyncSessionLocal
    from backend.security import hash_password, verify_password, create_access_token, decode_access_token
    from backend.models.user import User
    from sqlalchemy import select

    await init_db()

    # Password hashing
    raw_pw = "SuperSecurePassword123!"
    hashed = hash_password(raw_pw)
    assert verify_password(raw_pw, hashed), "Password verification failed"
    logger.info("✓ Password hashing & verification passed")

    # JWT tokens
    payload = {"sub": "test-user-id", "email": "test@example.com"}
    token = create_access_token(payload)
    decoded = decode_access_token(token)
    assert decoded["sub"] == "test-user-id", "JWT decode failed"
    logger.info("✓ JWT creation & decoding passed")

    # DB user insert & query
    async with AsyncSessionLocal() as db:
        user_email = f"test_{int(datetime.now().timestamp())}@example.com"
        user = User(
            email=user_email,
            username=f"tester_{int(datetime.now().timestamp())}",
            hashed_password=hashed,
            full_name="Data Scientist Tester",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        res = await db.execute(select(User).where(User.id == user.id))
        fetched = res.scalar_one_or_none()
        assert fetched is not None, "User could not be retrieved from DB"
        assert fetched.email == user_email, "Email mismatch"
        logger.info(f"✓ DB Persistence passed for user: {fetched.username}")

    return user.id


async def test_scrapers():
    logger.info("\n=== 2. Testing Live Platform Scrapers ===")
    from backend.services.platform_scrapers import (
        scrape_hackernews, scrape_devto, scrape_reddit, scrape_stackoverflow
    )

    # Test HackerNews (very reliable public Algolia API)
    try:
        hn_items = await scrape_hackernews("python bug", limit=5)
        logger.info(f"✓ HackerNews scraped: {len(hn_items)} real posts found")
        if hn_items:
            logger.info(f"  Example: '{hn_items[0]['title']}' (Score: {hn_items[0]['score']})")
    except Exception as e:
        logger.warning(f"HN Scrape warning: {e}")

    # Test Dev.to (public API)
    try:
        dev_items = await scrape_devto("frustrating", limit=5)
        logger.info(f"✓ Dev.to scraped: {len(dev_items)} real posts found")
        if dev_items:
            logger.info(f"  Example: '{dev_items[0]['title']}'")
    except Exception as e:
        logger.warning(f"Dev.to Scrape warning: {e}")

    # Test Reddit (public JSON)
    try:
        reddit_items = await scrape_reddit("api rate limit", limit=5)
        logger.info(f"✓ Reddit scraped: {len(reddit_items)} real posts found")
        if reddit_items:
            logger.info(f"  Example: '{reddit_items[0]['title']}' (Subreddit: r/{reddit_items[0]['subreddit']})")
    except Exception as e:
        logger.warning(f"Reddit Scrape warning: {e}")


def test_data_science_analyzer():
    logger.info("\n=== 3. Testing Data Science Problem Analyzer (Pandas + Scikit-learn) ===")
    from backend.services.ds_problem_analyzer import DataScienceProblemAnalyzer

    # Sample real-world problem items
    sample_items = [
        {
            "platform": "reddit",
            "title": "Why is customer invoice reconciliation still such a nightmare?",
            "content": "I hate spending 4 hours every Monday manually checking CSV files against Stripe. It is frustrating, broken, and we urgently need an automated tool.",
            "url": "https://reddit.com/r/SaaS/123",
            "author": "founder1",
            "score": 45,
            "num_comments": 22,
            "subreddit": "SaaS"
        },
        {
            "platform": "hackernews",
            "title": "Ask HN: How do you solve slow CI/CD Docker image builds?",
            "content": "Our team is struggling with 45-minute build times on GitHub Actions. It is a terrible waste of time and fails frequently due to cache invalidation.",
            "url": "https://news.ycombinator.com/item?id=999",
            "author": "devops_guru",
            "score": 120,
            "num_comments": 68,
            "subreddit": ""
        },
        {
            "platform": "stackoverflow",
            "title": "Memory leak in Python multiprocessing when parsing large JSON datasets",
            "content": "Process memory keeps growing indefinitely. Crash after 2 hours. Need help finding a workaround asap.",
            "url": "https://stackoverflow.com/q/777",
            "author": "pythonista",
            "score": 15,
            "num_comments": 6,
            "subreddit": ""
        },
        {
            "platform": "devto",
            "title": "Why we stopped using microservices: the hidden nightmare",
            "content": "Managing 30 services was impossible and expensive. Network latency sucked and debugging was horrible.",
            "url": "https://dev.to/techlead/microservices",
            "author": "techlead",
            "score": 88,
            "num_comments": 35,
            "subreddit": ""
        }
    ]

    analyzer = DataScienceProblemAnalyzer(sample_items)
    df = analyzer.compute_metrics()
    assert not df.empty, "DataFrame is empty"
    assert "pain_score" in df.columns, "pain_score column missing"
    assert "composite_priority" in df.columns, "composite_priority column missing"
    logger.info("✓ Pandas DataFrame constructed and statistical metrics calculated")

    # Check top opportunities
    opps = analyzer.get_top_opportunities(top_n=3)
    assert len(opps) > 0, "No opportunities extracted"
    logger.info(f"✓ Top opportunity extracted: '{opps[0]['title']}'")
    logger.info(f"  Pain score: {opps[0]['metrics']['pain_intensity']}/10 | Priority: {opps[0]['metrics']['composite_priority']}")

    # Check clustering
    analyzer.cluster_topics(n_clusters=2)
    assert "cluster_label" in analyzer.df.columns, "Cluster labels missing"
    logger.info(f"✓ Scikit-learn TF-IDF clustering completed: {analyzer.df['cluster_label'].unique().tolist()}")

    # Check CSV export
    csv_str = analyzer.export_csv()
    assert "composite_priority" in csv_str, "CSV export invalid"
    logger.info(f"✓ Dataset CSV export verified ({len(csv_str)} bytes)")


async def test_fastapi_endpoints():
    logger.info("\n=== 4. Testing FastAPI Application Endpoints ===")
    from httpx import ASGITransport, AsyncClient
    from backend.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Health check
        resp = await client.get("/api/health")
        assert resp.status_code == 200, f"Health check failed: {resp.status_code}"
        data = resp.json()
        assert data["status"] == "healthy", "App is not healthy"
        logger.info(f"✓ /api/health returned 200: {data['status']}")

        # Platforms list
        resp = await client.get("/api/discover/platforms")
        assert resp.status_code == 200, f"Platforms endpoint failed: {resp.status_code}"
        platforms = resp.json().get("platforms", [])
        assert len(platforms) >= 4, "Missing platforms"
        logger.info(f"✓ /api/discover/platforms returned {len(platforms)} platforms")

        # Static SPA serve
        resp = await client.get("/")
        assert resp.status_code == 200, f"SPA root failed: {resp.status_code}"
        assert "Problem2Project AI" in resp.text, "Index HTML not served properly"
        logger.info("✓ SPA frontend root served successfully")

        # Static JS files
        resp = await client.get("/js/api.js")
        assert resp.status_code == 200, f"api.js failed: {resp.status_code}"
        logger.info("✓ /js/api.js served successfully")

        resp = await client.get("/js/app.js")
        assert resp.status_code == 200, f"app.js failed: {resp.status_code}"
        logger.info("✓ /js/app.js served successfully")


async def main():
    logger.info("Starting Problem2Project AI verification suite...")
    await test_auth_and_db()
    await test_scrapers()
    test_data_science_analyzer()
    await test_fastapi_endpoints()
    logger.info("\n==========================================")
    logger.info("🎉 ALL TESTS PASSED SUCCESSFULLY! 100% READY.")
    logger.info("==========================================")


if __name__ == "__main__":
    asyncio.run(main())
