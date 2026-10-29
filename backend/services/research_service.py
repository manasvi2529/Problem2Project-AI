"""
Research service — live web search, source retrieval, evidence extraction.

Supports multiple search providers with graceful fallback.
"""
import logging
from datetime import datetime, timezone
from typing import Optional
import httpx
from bs4 import BeautifulSoup

from backend.config import settings

logger = logging.getLogger(__name__)

# ── Search Provider Implementations ──────────────────────────────────────────

async def search_google_custom(query: str, num_results: int = 10) -> list[dict]:
    """Search using Google Custom Search JSON API."""
    if not settings.SEARCH_API_KEY or not settings.SEARCH_ENGINE_ID:
        return []
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": settings.SEARCH_API_KEY,
        "cx": settings.SEARCH_ENGINE_ID,
        "q": query,
        "num": min(num_results, 10),
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    results = []
    for item in data.get("items", []):
        results.append({
            "url": item.get("link", ""),
            "title": item.get("title", ""),
            "snippet": item.get("snippet", ""),
            "publisher": item.get("displayLink", ""),
        })
    return results


async def search_serper(query: str, num_results: int = 10) -> list[dict]:
    """Search using Serper.dev API."""
    if not settings.SEARCH_API_KEY:
        return []
    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": settings.SEARCH_API_KEY, "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, headers=headers, json={"q": query, "num": num_results})
        resp.raise_for_status()
        data = resp.json()
    results = []
    for item in data.get("organic", []):
        results.append({
            "url": item.get("link", ""),
            "title": item.get("title", ""),
            "snippet": item.get("snippet", ""),
            "publisher": item.get("domain", ""),
        })
    return results


async def search_brave(query: str, num_results: int = 10) -> list[dict]:
    """Search using Brave Search API."""
    if not settings.SEARCH_API_KEY:
        return []
    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {"Accept": "application/json", "X-Subscription-Token": settings.SEARCH_API_KEY}
    params = {"q": query, "count": num_results}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
    results = []
    for item in data.get("web", {}).get("results", []):
        results.append({
            "url": item.get("url", ""),
            "title": item.get("title", ""),
            "snippet": item.get("description", ""),
            "publisher": item.get("meta_url", {}).get("hostname", ""),
        })
    return results


# ── Provider Dispatch ────────────────────────────────────────────────────────

SEARCH_PROVIDERS = {
    "google_custom": search_google_custom,
    "serper": search_serper,
    "brave": search_brave,
}


async def perform_web_search(query: str, num_results: int = 10) -> tuple[list[dict], str, bool]:
    """
    Execute web search using configured provider.
    Returns: (results, provider_name, is_live)
    """
    provider = settings.SEARCH_PROVIDER
    search_fn = SEARCH_PROVIDERS.get(provider)

    if not search_fn or not settings.search_configured:
        logger.warning(f"Search provider '{provider}' not configured. Returning empty results.")
        return [], provider, False

    try:
        results = await search_fn(query, num_results)
        return results, provider, True
    except Exception as e:
        logger.error(f"Search failed with provider '{provider}': {e}")
        return [], provider, False


# ── Page Content Extraction ──────────────────────────────────────────────────

async def fetch_page_content(url: str, max_chars: int = 15000) -> dict:
    """Fetch and extract text content from a web page."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Problem2ProjectAI/1.0 Research Bot"
            })
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove scripts and styles
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        # Truncate
        if len(text) > max_chars:
            text = text[:max_chars] + "... [truncated]"

        # Try to find publication date
        pub_date = None
        for meta in soup.find_all("meta"):
            prop = meta.get("property", "") or meta.get("name", "")
            if "date" in prop.lower() or "published" in prop.lower():
                pub_date = meta.get("content", "")
                break

        return {
            "text": text,
            "title": soup.title.string if soup.title else "",
            "publication_date": pub_date,
            "success": True,
        }
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return {"text": "", "title": "", "publication_date": None, "success": False, "error": str(e)}


# ── AI Analysis ──────────────────────────────────────────────────────────────

async def analyze_with_ai(prompt: str) -> Optional[str]:
    """Send a prompt to the configured AI provider and get a response."""
    if not settings.ai_configured:
        logger.warning("AI provider not configured")
        return None

    try:
        if settings.AI_PROVIDER == "google":
            from google import genai
            client = genai.Client(api_key=settings.GOOGLE_API_KEY)
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            return response.text
        elif settings.AI_PROVIDER == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
    except Exception as e:
        logger.error(f"AI analysis failed: {e}")
        return None


# ── Problem Extraction Prompt ────────────────────────────────────────────────

def build_analysis_prompt(query: str, sources: list[dict]) -> str:
    """Build a structured prompt for AI to extract problems from research sources."""
    source_text = ""
    for i, src in enumerate(sources, 1):
        source_text += f"\n--- Source {i}: {src.get('title', 'Unknown')} ---\n"
        source_text += f"URL: {src.get('url', '')}\n"
        source_text += f"Content: {src.get('text', src.get('snippet', ''))[:3000]}\n"

    return f"""You are a research analyst identifying real-world problems worth solving with technology.

Research Query: {query}

Sources found:
{source_text}

Analyze these sources and identify 3-5 distinct real-world problems. For each problem, provide a JSON array with objects containing:

1. "title": A clear problem statement (string)
2. "description": Detailed explanation of the problem (string)
3. "affected_users": Who is affected and estimated scale (string)
4. "existing_solutions": Current solutions and their limitations (string)
5. "solution_gaps": What's missing from current solutions (string)
6. "evidence_summary": Key evidence from the sources (string)
7. "claim_type": One of "verified_fact", "source_backed", "inference", "hypothesis"
8. "scores": An object with these dimensions, each having "score" (0-10), "explanation", and "confidence" ("high"/"medium"/"low"):
   - "severity": How serious is the problem
   - "scale": How many people are affected
   - "evidence_strength": How well-supported by sources
   - "urgency": How time-sensitive
   - "feasibility": How feasible to build a solution
   - "differentiation": How much room for a better solution
   - "effort": Estimated development effort (10=easy, 0=very hard)
9. "evidence_gaps": Array of strings — what evidence is missing
10. "contradictions": Array of strings — any conflicting evidence found

IMPORTANT:
- Only cite information actually present in the sources
- Mark claims appropriately: don't label inferences as verified facts
- Identify evidence gaps honestly
- Do NOT invent statistics, market sizes, or quotes

Return ONLY a valid JSON array. No markdown, no explanation outside the JSON."""


def build_scoring_weights() -> dict:
    """Default scoring weights for opportunity evaluation."""
    return {
        "severity": 0.15,
        "scale": 0.12,
        "evidence_strength": 0.15,
        "urgency": 0.10,
        "feasibility": 0.15,
        "differentiation": 0.13,
        "effort": 0.10,
        "data_availability": 0.10,
    }
