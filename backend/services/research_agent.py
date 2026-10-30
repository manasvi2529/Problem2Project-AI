"""
ProblemPilot AI — Dynamic Live Research Agent
Autonomous, prompt-driven research pipeline that parses user intent,
plans dynamic multi-source search strategies, extracts real-world evidence,
and tracks source credibility.
"""
import re
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import httpx

from backend.config import settings
from backend.services.research_service import perform_web_search, fetch_page_content, analyze_with_ai
from backend.services.platform_scrapers import (
    scrape_all_platforms, scrape_reddit, scrape_hackernews,
    scrape_stackoverflow, scrape_devto,
)

logger = logging.getLogger(__name__)


class ResearchAgent:
    """
    Intelligent research agent that dynamically investigates problems based on
    a user's natural language prompt.
    """

    @staticmethod
    def parse_user_prompt(prompt: str) -> Dict[str, Any]:
        """
        Extract user intent, geography, domain, skills, and constraints from freeform prompt.
        """
        p_lower = prompt.lower()

        # Geography detection
        geography = ""
        geo_keywords = {
            "india": "India", "us": "United States", "usa": "United States",
            "uk": "United Kingdom", "europe": "Europe", "germany": "Germany",
            "global": "Global", "asia": "Asia", "canada": "Canada"
        }
        for kw, name in geo_keywords.items():
            if re.search(rf"\b{kw}\b", p_lower):
                geography = name
                break

        # Tech stack / skills detection
        tech_matches = []
        tech_keywords = [
            "python", "sql", "react", "fastapi", "docker", "machine learning",
            "ai", "data science", "node", "typescript", "golang", "rust",
            "postgres", "mongodb", "aws", "kubernetes", "flutter", "nextjs"
        ]
        for tech in tech_keywords:
            if re.search(rf"\b{re.escape(tech)}\b", p_lower):
                tech_matches.append(tech)

        # Goal detection
        goal = "portfolio_project"
        if "startup" in p_lower or "business" in p_lower or "monetize" in p_lower or "saas" in p_lower:
            goal = "startup_opportunity"
        elif "placement" in p_lower or "resume" in p_lower or "interview" in p_lower or "job" in p_lower:
            goal = "career_placement"
        elif "learning" in p_lower or "beginner" in p_lower:
            goal = "skill_mastery"

        # Domain / industry detection
        domain = "software_engineering"
        domain_keywords = {
            "fintech": ["invoice", "payment", "bank", "finance", "tax", "accounting"],
            "healthcare": ["health", "medical", "patient", "clinic", "hospital", "doctor"],
            "education": ["student", "teacher", "learn", "course", "college", "school"],
            "devops": ["ci/cd", "docker", "kubernetes", "deploy", "infrastructure", "cloud", "monitoring"],
            "e-commerce": ["store", "inventory", "shipping", "order", "retail", "marketplace"],
            "developer_tools": ["api", "debugger", "cli", "sdk", "compiler", "linter", "git"],
            "data_analytics": ["dataset", "pipeline", "etl", "visualization", "bi", "metrics"],
        }
        for d_name, kws in domain_keywords.items():
            if any(kw in p_lower for kw in kws):
                domain = d_name
                break

        return {
            "original_prompt": prompt,
            "geography": geography,
            "skills": tech_matches,
            "goal": goal,
            "domain": domain,
        }

    @staticmethod
    def formulate_search_queries(intent: Dict[str, Any]) -> List[str]:
        """Generate targeted search queries across multiple problem angles."""
        prompt = intent["original_prompt"]
        geo = intent.get("geography", "")
        domain = intent.get("domain", "")

        queries = [
            f"{prompt} problem pain point challenges",
            f"biggest problems in {domain} {geo}".strip(),
            f"frustrating manual workflow {domain} {geo}".strip(),
            f"why is {domain} tooling broken {geo}".strip(),
        ]
        return [q for q in queries if len(q) > 5][:4]

    async def execute_live_research(self, prompt: str) -> Dict[str, Any]:
        """
        Execute comprehensive live research across the web and developer communities.
        """
        intent = self.parse_user_prompt(prompt)
        queries = self.formulate_search_queries(intent)

        gathered_sources: List[Dict[str, Any]] = []
        raw_discussions: List[Dict[str, Any]] = []

        # 1. Scrape developer communities for live user frustration
        try:
            platform_results = await scrape_all_platforms(prompt, limit=5)
            for plat, items in platform_results.get("results", {}).items():
                for item in items:
                    raw_discussions.append(item)
                    gathered_sources.append({
                        "url": item.get("url", ""),
                        "title": item.get("title", ""),
                        "publisher": f"{plat} ({item.get('author', 'community')})",
                        "snippet": item.get("content", "")[:400],
                        "full_text": item.get("content", "")[:2000],
                        "source_type": plat,
                        "relevance_score": float(item.get("score", 1.0)),
                        "reliability": "high" if item.get("score", 0) > 10 else "medium",
                        "claim_type": "source_reported",
                        "retrieval_date": datetime.now(timezone.utc).isoformat(),
                    })
        except Exception as e:
            logger.warning(f"Community scraping partial failure: {e}")

        # 2. Perform live web search for industry reports and articles
        for q in queries[:2]:
            try:
                web_res, provider, is_live = await perform_web_search(q, num_results=4)
                for item in web_res:
                    # Fetch page snippet/text
                    page_data = await fetch_page_content(item["url"])
                    gathered_sources.append({
                        "url": item["url"],
                        "title": item.get("title") or page_data.get("title", ""),
                        "publisher": item.get("publisher", "Web"),
                        "snippet": item.get("snippet", "") or page_data.get("text", "")[:300],
                        "full_text": page_data.get("text", "")[:2000],
                        "source_type": "web",
                        "relevance_score": 8.0,
                        "reliability": "high" if any(k in item["url"] for k in [".gov", ".edu", ".org", "github.com", "ycombinator.com"]) else "medium",
                        "claim_type": "source_reported",
                        "retrieval_date": datetime.now(timezone.utc).isoformat(),
                    })
            except Exception as e:
                logger.warning(f"Web search query '{q}' error: {e}")

        return {
            "intent": intent,
            "queries": queries,
            "sources": gathered_sources,
            "raw_discussions": raw_discussions,
            "total_evidence_pieces": len(gathered_sources),
            "researched_at": datetime.now(timezone.utc).isoformat(),
        }

