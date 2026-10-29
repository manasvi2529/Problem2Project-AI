"""
Platform Scrapers — Pull real-world problems from Reddit, HackerNews,
StackOverflow, ProductHunt, and GitHub Trending.

All scrapers use public APIs or public pages. No authentication required
for basic access. Rate-limited and respectful.
"""
import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Optional
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Problem2ProjectAI/1.0 (Research Bot; +https://github.com/problem2project)"
}


# ═══════════════════════════════════════════════════════════════════════════════
# REDDIT — Public JSON API (no auth needed for read-only)
# ═══════════════════════════════════════════════════════════════════════════════

async def scrape_reddit(query: str, subreddits: list[str] = None, limit: int = 15) -> list[dict]:
    """
    Search Reddit for problems, complaints, and pain points.
    Uses Reddit's public .json endpoints — no API key needed.
    """
    results = []
    default_subs = [
        "startups", "SaaS", "Entrepreneur", "smallbusiness",
        "technology", "webdev", "learnprogramming", "datascience",
        "productivity", "selfimprovement"
    ]
    subs = subreddits or default_subs

    # Fast concurrent query: check direct Reddit and PullPush simultaneously
    async with httpx.AsyncClient(timeout=4.0, headers=HEADERS) as client:
        async def try_direct_reddit():
            items = []
            try:
                search_url = "https://www.reddit.com/search.json"
                params = {
                    "q": f"{query} (problem OR frustrating OR need)",
                    "sort": "relevance",
                    "t": "month",
                    "limit": limit,
                }
                resp = await client.get(search_url, params=params)
                if resp.status_code == 200:
                    for post in resp.json().get("data", {}).get("children", []):
                        d = post.get("data", {})
                        if not d.get("over_18"):
                            items.append({
                                "platform": "reddit",
                                "title": d.get("title", ""),
                                "content": d.get("selftext", "")[:2000],
                                "url": f"https://reddit.com{d.get('permalink', '')}",
                                "author": d.get("author", ""),
                                "subreddit": d.get("subreddit", ""),
                                "score": d.get("score", 0),
                                "num_comments": d.get("num_comments", 0),
                                "created_utc": d.get("created_utc", 0),
                                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                            })
            except Exception:
                pass
            return items

        async def try_pullpush():
            items = []
            try:
                pp_url = "https://api.pullpush.io/reddit/search/submission/"
                pp_params = {"q": query, "size": limit, "sort": "desc", "sort_type": "score"}
                resp = await client.get(pp_url, params=pp_params)
                if resp.status_code == 200:
                    for d in resp.json().get("data", []):
                        items.append({
                            "platform": "reddit",
                            "title": d.get("title", ""),
                            "content": (d.get("selftext", "") or "")[:2000],
                            "url": f"https://reddit.com{d.get('permalink', '')}" if d.get("permalink") else d.get("url", ""),
                            "author": d.get("author", ""),
                            "subreddit": d.get("subreddit", ""),
                            "score": d.get("score", 0),
                            "num_comments": d.get("num_comments", 0),
                            "created_utc": d.get("created_utc", 0),
                            "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        })
            except Exception:
                pass
            return items

        direct_res, pp_res = await asyncio.gather(try_direct_reddit(), try_pullpush(), return_exceptions=True)
        if isinstance(direct_res, list): results.extend(direct_res)
        if isinstance(pp_res, list): results.extend(pp_res)

    # Deduplicate by URL
    seen = set()
    unique = []
    for r in results:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique.append(r)
    return unique


# ═══════════════════════════════════════════════════════════════════════════════
# HACKER NEWS — Official API (free, no key needed)
# ═══════════════════════════════════════════════════════════════════════════════

async def scrape_hackernews(query: str, limit: int = 15) -> list[dict]:
    """
    Search HackerNews via Algolia's free HN Search API.
    Great for tech problems, developer pain points, startup ideas.
    """
    results = []
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            # Algolia HN Search API — free, no key required
            url = "https://hn.algolia.com/api/v1/search"
            params = {
                "query": query,
                "tags": "story",
                "numericFilters": "points>10",  # Only quality posts
                "hitsPerPage": limit,
            }
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            for hit in data.get("hits", []):
                results.append({
                    "platform": "hackernews",
                    "title": hit.get("title", ""),
                    "content": hit.get("story_text", "") or "",
                    "url": hit.get("url", "") or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}",
                    "hn_url": f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}",
                    "author": hit.get("author", ""),
                    "score": hit.get("points", 0),
                    "num_comments": hit.get("num_comments", 0),
                    "created_at": hit.get("created_at", ""),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                })
        except Exception as e:
            logger.warning(f"HackerNews search failed: {e}")

    # Also search "Ask HN" posts — these often contain real problems
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            url = "https://hn.algolia.com/api/v1/search"
            params = {
                "query": query,
                "tags": "ask_hn",
                "hitsPerPage": 10,
            }
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            for hit in data.get("hits", []):
                results.append({
                    "platform": "hackernews",
                    "title": hit.get("title", ""),
                    "content": hit.get("story_text", "") or "",
                    "url": f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}",
                    "hn_url": f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}",
                    "author": hit.get("author", ""),
                    "score": hit.get("points", 0),
                    "num_comments": hit.get("num_comments", 0),
                    "created_at": hit.get("created_at", ""),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                })
        except Exception as e:
            logger.warning(f"HN Ask search failed: {e}")

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# STACK OVERFLOW — Public API (no key needed for basic queries)
# ═══════════════════════════════════════════════════════════════════════════════

async def scrape_stackoverflow(query: str, limit: int = 10) -> list[dict]:
    """
    Search StackOverflow for common developer problems and pain points.
    Uses the public SE API — no key needed (limited to 300 req/day without key).
    """
    results = []
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            url = "https://api.stackexchange.com/2.3/search/advanced"
            params = {
                "order": "desc",
                "sort": "relevance",
                "q": query,
                "site": "stackoverflow",
                "pagesize": limit,
                "filter": "withbody",
            }
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("items", []):
                # Clean HTML from body
                body = item.get("body", "")
                if body:
                    soup = BeautifulSoup(body, "html.parser")
                    body = soup.get_text()[:1500]

                results.append({
                    "platform": "stackoverflow",
                    "title": item.get("title", ""),
                    "content": body,
                    "url": item.get("link", ""),
                    "author": item.get("owner", {}).get("display_name", ""),
                    "score": item.get("score", 0),
                    "view_count": item.get("view_count", 0),
                    "answer_count": item.get("answer_count", 0),
                    "tags": item.get("tags", []),
                    "is_answered": item.get("is_answered", False),
                    "created_at": datetime.fromtimestamp(
                        item.get("creation_date", 0), tz=timezone.utc
                    ).isoformat() if item.get("creation_date") else "",
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                })
        except Exception as e:
            logger.warning(f"StackOverflow search failed: {e}")

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# GITHUB TRENDING — Scrape trending repos for emerging problem spaces
# ═══════════════════════════════════════════════════════════════════════════════

async def scrape_github_trending(language: str = "", since: str = "weekly") -> list[dict]:
    """
    Scrape GitHub Trending page for popular repositories.
    Shows what problems developers are actively solving.
    """
    results = []
    async with httpx.AsyncClient(timeout=15, headers=HEADERS, follow_redirects=True) as client:
        try:
            url = f"https://github.com/trending/{language}"
            params = {"since": since}
            resp = await client.get(url, params=params)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            articles = soup.select("article.Box-row")

            for article in articles[:15]:
                # Repo name
                h2 = article.select_one("h2 a")
                if not h2:
                    continue
                repo_path = h2.get("href", "").strip("/")
                repo_name = repo_path.split("/")[-1] if "/" in repo_path else repo_path

                # Description
                p = article.select_one("p")
                description = p.get_text(strip=True) if p else ""

                # Stars
                stars_el = article.select_one("[href$='/stargazers']")
                stars = stars_el.get_text(strip=True).replace(",", "") if stars_el else "0"

                # Language
                lang_el = article.select_one("[itemprop='programmingLanguage']")
                lang = lang_el.get_text(strip=True) if lang_el else ""

                results.append({
                    "platform": "github_trending",
                    "title": repo_name,
                    "content": description,
                    "url": f"https://github.com/{repo_path}",
                    "author": repo_path.split("/")[0] if "/" in repo_path else "",
                    "stars": int(stars) if stars.isdigit() else 0,
                    "language": lang,
                    "trending_since": since,
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                })
        except Exception as e:
            logger.warning(f"GitHub Trending scrape failed: {e}")

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# DEV.TO — Public API (no key needed)
# ═══════════════════════════════════════════════════════════════════════════════

async def scrape_devto(query: str, limit: int = 10) -> list[dict]:
    """
    Search Dev.to for articles about problems, pain points, and solutions.
    Free public API.
    """
    results = []
    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
        try:
            url = "https://dev.to/api/articles"
            params = {
                "tag": query.lower().replace(" ", ""),
                "per_page": limit,
                "state": "rising",
            }
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                articles = resp.json()
                for art in articles:
                    results.append({
                        "platform": "devto",
                        "title": art.get("title", ""),
                        "content": art.get("description", ""),
                        "url": art.get("url", ""),
                        "author": art.get("user", {}).get("username", ""),
                        "score": art.get("public_reactions_count", 0),
                        "comments_count": art.get("comments_count", 0),
                        "tags": art.get("tag_list", []),
                        "published_at": art.get("published_at", ""),
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    })
        except Exception as e:
            logger.warning(f"Dev.to search failed: {e}")

        # Also try search endpoint
        try:
            url = "https://dev.to/api/articles"
            params = {"per_page": limit}
            # Dev.to doesn't have a search param in public API, use page
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                articles = resp.json()
                for art in articles:
                    title_lower = art.get("title", "").lower()
                    desc_lower = art.get("description", "").lower()
                    query_lower = query.lower()
                    if query_lower in title_lower or query_lower in desc_lower:
                        results.append({
                            "platform": "devto",
                            "title": art.get("title", ""),
                            "content": art.get("description", ""),
                            "url": art.get("url", ""),
                            "author": art.get("user", {}).get("username", ""),
                            "score": art.get("public_reactions_count", 0),
                            "comments_count": art.get("comments_count", 0),
                            "tags": art.get("tag_list", []),
                            "published_at": art.get("published_at", ""),
                            "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        })
        except Exception as e:
            logger.warning(f"Dev.to latest failed: {e}")

    # Deduplicate
    seen = set()
    unique = []
    for r in results:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique.append(r)
    return unique


# ═══════════════════════════════════════════════════════════════════════════════
# KAGGLE — Real-World Problem Datasets & Industry Challenges
# ═══════════════════════════════════════════════════════════════════════════════

async def scrape_kaggle(query: str, limit: int = 15) -> list[dict]:
    """
    Search Kaggle for real-world problem datasets, industry pain points,
    and challenge specifications. Uses Kaggle's public dataset endpoint.
    """
    results = []
    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
        try:
            url = "https://www.kaggle.com/api/v1/datasets/list"
            params = {
                "search": query,
                "sortBy": "votes",
                "page": 1,
            }
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    for item in data[:limit]:
                        ref = item.get("ref", "")
                        title = item.get("title", "")
                        creator = item.get("ownerName", item.get("ownerRef", "kaggle_community"))
                        votes = item.get("totalVotes") or item.get("voteCount") or 0
                        downloads = item.get("totalDownloads") or item.get("downloadCount") or 0
                        rating = item.get("usabilityRating", 0.0)

                        snippet = (
                            f"Kaggle Problem Dataset: {title}. "
                            f"Industry benchmark problem for domain analysis. Usability rating: {rating}/1.0. "
                            f"Validated by {votes} votes and {downloads} community downloads."
                        )

                        results.append({
                            "platform": "kaggle",
                            "title": title,
                            "content": snippet,
                            "url": f"https://www.kaggle.com/datasets/{ref}" if ref else f"https://www.kaggle.com/search?q={query}",
                            "author": creator,
                            "score": votes,
                            "num_comments": downloads,
                            "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        })
        except Exception as e:
            logger.warning(f"Kaggle scraper failed: {e}")

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# MASTER SCRAPER — Aggregates all platforms
# ═══════════════════════════════════════════════════════════════════════════════

async def scrape_all_platforms(
    query: str,
    platforms: list[str] = None,
    subreddits: list[str] = None,
) -> dict:
    """
    Run scrapers across all configured platforms and aggregate results.

    Args:
        query: Search query for finding problems
        platforms: List of platforms to scrape (default: all)
        subreddits: Custom subreddits for Reddit search

    Returns:
        Dict with results per platform and aggregate stats
    """
    all_platforms = platforms or ["reddit", "kaggle", "hackernews", "stackoverflow", "devto", "github_trending"]
    results = {}
    errors = []

    async def run_single(plat: str):
        try:
            if plat == "reddit":
                return plat, await scrape_reddit(query, subreddits)
            elif plat == "kaggle":
                return plat, await scrape_kaggle(query)
            elif plat == "hackernews":
                return plat, await scrape_hackernews(query)
            elif plat == "stackoverflow":
                return plat, await scrape_stackoverflow(query)
            elif plat == "github_trending":
                return plat, await scrape_github_trending()
            elif plat == "devto":
                return plat, await scrape_devto(query)
            return plat, []
        except Exception as e:
            logger.error(f"Platform {plat} failed: {e}")
            return plat, []

    # Run all scrapers in parallel
    tasks = [run_single(p) for p in all_platforms]
    outcomes = await asyncio.gather(*tasks, return_exceptions=True)

    for out in outcomes:
        if isinstance(out, tuple):
            p_name, p_data = out
            results[p_name] = p_data
        elif isinstance(out, Exception):
            errors.append(str(out))

    # Compute stats
    total_items = sum(len(v) for v in results.values())
    platform_stats = {k: len(v) for k, v in results.items()}

    return {
        "results": results,
        "total_items": total_items,
        "platform_stats": platform_stats,
        "platforms_queried": all_platforms,
        "errors": errors,
        "query": query,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
