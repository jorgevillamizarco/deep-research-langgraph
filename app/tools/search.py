"""Web search tool wrapper.

Factory function that returns a search backend with this priority:
1. Tavily if TAVILY_API_KEY is set
2. SearXNG if SEARXNG_URL is set (default: http://localhost:8080)
3. DuckDuckGo as fallback
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.parse
import warnings
from typing import Any

import warnings

warnings.filterwarnings("ignore", message=".*duckduckgo_search.*renamed.*")

from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

_DEFAULT_SEARXNG_URL = "http://localhost:8080"


# ──────────────────────────────────────────────
# DuckDuckGo backend
# ──────────────────────────────────────────────


def _duckduckgo_search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Execute a web search via DuckDuckGo and return structured results."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                }
                for r in results
            ]
    except Exception as e:
        logger.warning("DuckDuckGo search failed for query %r: %s", query, e)
        return []


# ──────────────────────────────────────────────
# Tavily backend
# ──────────────────────────────────────────────


def _tavily_search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Execute a web search via Tavily."""
    try:
        from langchain_community.tools.tavily_search import TavilySearchResults

        tool = TavilySearchResults(max_results=max_results)
        raw = tool.invoke({"query": query})
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", r.get("snippet", "")),
            }
            for r in raw
        ]
    except Exception as e:
        logger.warning("Tavily search failed for query %r: %s", query, e)
        return []


# ──────────────────────────────────────────────
# SearXNG backend
# ──────────────────────────────────────────────


def _searxng_search(
    query: str, max_results: int = 5, base_url: str | None = None
) -> list[dict[str, Any]]:
    """Execute a web search via a local SearXNG instance.

    Args:
        query: The search query string.
        max_results: Max results to return.
        base_url: SearXNG base URL (default: env SEARXNG_URL or http://localhost:8080).

    Returns:
        List of {title, url, snippet} dicts.
    """
    import httpx

    url = base_url or os.getenv("SEARXNG_URL", _DEFAULT_SEARXNG_URL)
    params = {
        "q": query,
        "format": "json",
        "language": "en",
        "categories": "general,web",
        "pageno": 1,
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(
                f"{url.rstrip('/')}/search",
                params=params,
                headers={
                    "User-Agent": "LangGraph-DeepResearch-Agent/1.0",
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for r in data.get("results", []):
            results.append(
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", r.get("snippet", "")),
                }
            )

        logger.info(
            "SearXNG returned %d results for %r (from %d total)",
            len(results),
            query[:60],
            data.get("number_of_results", 0),
        )
        return results[:max_results]

    except Exception as e:
        logger.warning("SearXNG search failed for query %r: %s", query, e)
        return []


# ──────────────────────────────────────────────
# Factory
# ──────────────────────────────────────────────


def get_search_tool() -> Any:
    """Return a search-callable with backend priority: Tavily > SearXNG > DuckDuckGo.

    The returned object has a .invoke({query, ...}) interface compatible with
    LangChain tools.

    Returns:
        An object with an ``invoke(params: dict) -> list[dict]`` method.
    """
    if os.getenv("TAVILY_API_KEY"):
        logger.info("Using Tavily search backend")
        return _SearchWrapper(_tavily_search)

    searxng_url = os.getenv("SEARXNG_URL", _DEFAULT_SEARXNG_URL)
    # Check if SearXNG is available by hitting its health endpoint
    try:
        import httpx

        with httpx.Client(timeout=3.0) as client:
            resp = client.get(f"{searxng_url.rstrip('/')}/search?q=health&format=json")
            if resp.status_code == 200:
                logger.info("Using SearXNG search backend at %s", searxng_url)
                return _SearchWrapper(_searxng_search)
    except Exception:
        pass

    logger.info("Using DuckDuckGo search backend (fallback)")
    return _SearchWrapper(_duckduckgo_search)


# ──────────────────────────────────────────────
# Adapter
# ──────────────────────────────────────────────


class _SearchWrapper:
    """Adapter to present any search backend as a callable."""

    def __init__(self, impl):
        self._impl = impl

    def invoke(self, params: dict) -> list[dict]:
        query = params.get("query", "")
        max_results = params.get("max_results", 5)
        if not query:
            return []
        return self._impl(query, max_results=max_results)


# ──────────────────────────────────────────────
# Formatting
# ──────────────────────────────────────────────


def format_search_results(query: str, results: list[dict]) -> str:
    """Format search results for inclusion in an LLM prompt."""
    if not results:
        return f"### Search Results: {query}\nNo results found.\n"
    lines = [f"### Search Results: {query}"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "Untitled")
        url = r.get("url", "")
        snippet = r.get("snippet", "")
        lines.append(f"{i}. [{title}]({url})")
        if snippet:
            lines.append(f"   > {snippet[:300]}")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# URL Content Fetching
# ──────────────────────────────────────────────


def fetch_url_content(url: str, max_chars: int = 8000) -> str:
    """Fetch and extract readable text content from a URL.

    Downloads the page via HTTP, strips HTML tags, and returns
    clean text suitable for LLM consumption. Truncates to max_chars.

    If HTTP extraction yields too little content (<500 chars), falls back
    to headless browser (Playwright + Chromium) for JavaScript-rendered pages.

    Returns empty string on failure (network error, timeout, etc.).
    """
    import re as _re

    # First attempt: HTTP extraction (fast, works for most static pages)
    text = _fetch_via_http(url, max_chars)
    if text and len(text) >= 500:
        return text[:max_chars]

    # Second attempt: headless browser (JS-rendered pages, SPAs)
    if text and len(text) < 500:
        logger.info("HTTP extraction returned only %d chars from %s, "
                     "trying browser fallback", len(text), url[:80])
    else:
        logger.info("HTTP extraction failed for %s, "
                     "trying browser fallback", url[:80])

    browser_text = _fetch_via_browser(url, max_chars)
    if browser_text:
        return browser_text[:max_chars]

    # Return whatever HTTP got, even if sparse
    return text[:max_chars]


def _fetch_via_http(url: str, max_chars: int = 8000) -> str:
    """Extract text from URL via HTTP request + HTML stripping."""
    import re as _re

    try:
        import httpx
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(url, headers={
                "User-Agent": "DeepResearch-MCP/1.0 (research agent; text extraction only)",
                "Accept": "text/html,application/xhtml+xml,*/*",
            })
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        logger.warning("URL fetch failed for %s: %s", url[:80], e)
        return ""

    if not html:
        return ""

    # Strip scripts, styles, and non-content tags
    for tag in ["script", "style", "head", "nav", "footer", "header"]:
        html = _re.sub(f"<{tag}[^>]*>.*?</{tag}>", "", html, flags=_re.DOTALL | _re.IGNORECASE)

    # Strip HTML tags
    html = _re.sub(r"<[^>]+>", "\n", html)

    # Decode HTML entities
    html = html.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    html = html.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")

    # Clean whitespace: collapse blank lines
    lines = [line.strip() for line in html.splitlines() if line.strip()]
    text = "\n".join(lines)
    return text


def _fetch_via_browser(url: str, max_chars: int = 8000) -> str:
    """Extract text from URL via headless Playwright Chromium.

    Falls back gracefully if Playwright is not installed.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.debug("Playwright not installed — browser extraction unavailable")
        return ""

    try:
        with sync_playwright() as p:
            # Use system Chromium if installed (apt), fall back to Playwright's bundled
            launch_args: dict = {"headless": True}
            import shutil
            chromium_path = shutil.which("chromium") or shutil.which("chromium-browser")
            if chromium_path:
                launch_args["executable_path"] = chromium_path
            browser = p.chromium.launch(**launch_args)
            page = browser.new_page()
            # Navigate and wait for network to be mostly idle
            page.goto(url, wait_until="networkidle", timeout=20000)
            # Wait a beat for lazy-loaded content
            page.wait_for_timeout(1000)
            # Extract visible text from the page body
            text = page.evaluate("""
                () => {
                    // Remove script, style, nav, footer elements
                    for (const el of document.querySelectorAll(
                        'script, style, nav, footer, header, [role="navigation"]'
                    )) el.remove();
                    return document.body ? document.body.innerText : "";
                }
            """)
            browser.close()
            # Clean up whitespace
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            return "\n".join(lines)
    except Exception as e:
        logger.warning("Browser extraction failed for %s: %s", url[:80], e)
        return ""
