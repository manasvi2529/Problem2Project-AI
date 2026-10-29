"""Quick test for Kaggle scraper, LLM Agent synthesis, and ProjectDeployer."""
import asyncio
from backend.services.platform_scrapers import scrape_kaggle
from backend.services.llm_agent import LLMAgent
from backend.services.project_deployer import ProjectDeployer

import sys

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

async def test():
    print("1. Testing live Kaggle scraping...")
    kaggle_items = await scrape_kaggle("churn", limit=3)
    print(f"[OK] Kaggle items fetched: {len(kaggle_items)}")
    if kaggle_items:
        print(f"  Example: '{kaggle_items[0]['title']}' (Score: {kaggle_items[0]['score']})")

    print("\n2. Testing LLM Agent Domain Synthesis...")
    agent = LLMAgent()
    opps = await agent.synthesize_domain_opportunities("ai_ml", kaggle_items, num_opportunities=2)
    print(f"[OK] Domain opportunities generated: {len(opps)}")
    print(f"  Opportunity 1: '{opps[0]['title']}'")
    print(f"  Problem: '{opps[0]['problem'][:80]}...'")
    print(f"  Solution: '{opps[0]['solution'][:80]}...'")

    print("\n3. Testing Full Application Code Synthesis...")
    files = await agent.generate_application_files(
        problem=opps[0]['problem'],
        solution=opps[0]['solution'],
        cs_domain=opps[0]['cs_domain'],
        project_name="Test-AI-Project",
    )
    print(f"[OK] Generated {len(files)} files: {list(files.keys())}")

    print("\n4. Testing Autonomous Deployer & Git Initializer...")
    result = ProjectDeployer.deploy_application("test-ai-project", files, preferred_port=8025)
    print(f"[OK] Project deployed successfully!")
    print(f"  URL: {result['url']}")
    print(f"  Git commit: {result['git_commit']}")
    print(f"  Files created: {result['files_created']}")

    print("\n[OK] ALL TESTS PASSED!")

if __name__ == "__main__":
    asyncio.run(test())
