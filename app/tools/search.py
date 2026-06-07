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
import unicodedata
import urllib.parse
from typing import Any

try:
    from ddgs import DDGS
except ImportError:  # pragma: no cover - compatibility for older local venvs
    from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

_DEFAULT_SEARXNG_URL = "http://localhost:8080"
_DDGS_REGION_BY_LANG = {
    "en": "us-en",
    "es": "es-es",
    "de": "de-de",
    "fr": "fr-fr",
    "it": "it-it",
    "pt": "pt-pt",
    "ca": "es-ca",
}


# ──────────────────────────────────────────────
# DuckDuckGo backend
# ──────────────────────────────────────────────


def _duckduckgo_search(
    query: str,
    max_results: int = 5,
    language: str | None = None,
) -> list[dict[str, Any]]:
    """Execute a web search via DuckDuckGo and return structured results."""
    try:
        with DDGS() as ddgs:
            results = list(
                ddgs.text(
                    query,
                    max_results=max_results,
                    region=_resolve_ddgs_region(query, language),
                )
            )
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


def _tavily_search(
    query: str,
    max_results: int = 5,
    language: str | None = None,
) -> list[dict[str, Any]]:
    """Execute a web search via Tavily."""
    if _resolve_search_language(query, language) != "en" and _searxng_is_reachable():
        logger.info("Routing non-English query to SearXNG for language-aware search: %r", query)
        return _searxng_search(query, max_results=max_results, language=language)
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
    query: str,
    max_results: int = 5,
    base_url: str | None = None,
    language: str | None = None,
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
        "language": _resolve_search_language(query, language),
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

    if _searxng_is_reachable():
        logger.info("Using SearXNG search backend at %s", os.getenv("SEARXNG_URL", _DEFAULT_SEARXNG_URL))
        return _SearchWrapper(_searxng_search)

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
        language = params.get("language")
        if not query:
            return []
        return self._impl(query, max_results=max_results, language=language)


def _resolve_ddgs_region(query: str, language: str | None = None) -> str:
    """Map the resolved search language to a DDGS region code."""
    code = _resolve_search_language(query, language)
    return _DDGS_REGION_BY_LANG.get(code, "us-en")


def _searxng_is_reachable(base_url: str | None = None) -> bool:
    """Return True when the configured SearXNG endpoint answers a quick probe."""
    import httpx

    searxng_url = base_url or os.getenv("SEARXNG_URL", _DEFAULT_SEARXNG_URL)
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(f"{searxng_url.rstrip('/')}/search?q=health&format=json")
        return resp.status_code == 200
    except Exception:
        return False


def _resolve_search_language(query: str, language: str | None = None) -> str:
    """Resolve a SearXNG language code from an explicit hint or query text."""
    explicit = _normalize_language_hint(language)
    if explicit:
        return explicit
    inferred = _infer_language_from_query(query)
    return inferred or "en"


def _normalize_language_hint(language: str | None) -> str | None:
    """Map free-form language hints to SearXNG language codes."""
    if not language:
        return None
    normalized = unicodedata.normalize("NFKD", language)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-zA-Z_-]", " ", ascii_text).strip().lower()
    aliases = {
        "en": "en", "english": "en",
        "es": "es", "spanish": "es", "espanol": "es", "castilian": "es",
        "de": "de", "german": "de", "deutsch": "de",
        "fr": "fr", "french": "fr", "francais": "fr",
        "it": "it", "italian": "it", "italiano": "it",
        "pt": "pt", "portuguese": "pt", "portugues": "pt",
        "ca": "ca", "catalan": "ca", "catala": "ca",
    }
    for token in cleaned.replace("-", " ").replace("_", " ").split():
        if token in aliases:
            return aliases[token]
    return None


def _infer_language_from_query(query: str) -> str | None:
    """Infer a likely query language from obvious lexical signals."""
    lower = f" {query.lower()} "
    if re.search(r"[äöüß]", lower) or any(term in lower for term in (
        " gesetz ", " urteil ", " deutschland ", " verordnung ",
    )):
        return "de"
    if re.search(r"[ñáéíóú]", lower) or any(term in lower for term in (
        " nacionalidad ", " certificado ", " residencia ", " tribunal ",
        " ley ", " decreto ", " españa ", " español ", " española ", " validez ",
    )):
        return "es"
    if re.search(r"[àâçéèêëîïôûùüÿœæ]", lower) or any(term in lower for term in (
        " france ", " décret ", " tribunal administratif ", " droit ",
    )):
        return "fr"
    return None


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
    if text and len(text) >= 500 and not _is_error_page(text):
        return text[:max_chars]

    # Second attempt: headless browser (JS-rendered pages, SPAs, error pages)
    if text:
        reason = "error page" if _is_error_page(text) else f"only {len(text)} chars"
        logger.info("HTTP extraction %s from %s, trying browser fallback", reason, url[:80])
    else:
        logger.info("HTTP extraction failed for %s, trying browser fallback", url[:80])

    browser_text = _fetch_via_browser(url, max_chars, follow_links=3)  # follow 3 relevant links (more for deep navigation)
    if browser_text:
        return browser_text[:max_chars]

    # Return whatever HTTP got, even if sparse
    return text[:max_chars]


def _is_error_page(text: str) -> bool:
    """Detect if extracted text looks like a 404/error page rather than real content."""
    if not text:
        return False
    lower = text.lower()
    # HTTP error indicators (language-agnostic patterns)
    # Check these FIRST — even short error messages should be caught
    error_signals = [
        "404 not found", "403 forbidden", "500 internal server",
        "page not found", "no encontrada", "página no encontrada",
        "no encontrado", "no existe", "does not exist",
        "the requested url was not found", "erreur 404",
        "nicht gefunden", "非表示",  # German, Japanese
    ]
    if any(signal in lower for signal in error_signals):
        return True
    # For pages without explicit error text: check if it's boilerplate
    if len(text) < 100:
        return False  # too short to classify without error keywords
    # Suspicious: short pages with very few substantive words
    if len(text) < 300:
        words = [w for w in text.split() if len(w) > 6]
        if len(words) < 3:
            return True
    return False


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


def _fetch_via_browser(url: str, max_chars: int = 8000, follow_links: int = 0) -> str:
    """Extract text from URL via headless Playwright Chromium.

    Args:
        url: The URL to fetch.
        max_chars: Maximum characters per page.
        follow_links: If >0, also follow this many relevant links on the page
                     and include their content. Adds ~20s per followed link.

    Falls back gracefully if Playwright is not installed.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.debug("Playwright not installed — browser extraction unavailable")
        return ""

    try:
        with sync_playwright() as p:
            launch_args: dict = {"headless": True}
            import shutil
            chromium_path = shutil.which("chromium") or shutil.which("chromium-browser")
            if chromium_path:
                launch_args["executable_path"] = chromium_path
            browser = p.chromium.launch(**launch_args)
            page = browser.new_page()

            # Navigate and wait for network to be mostly idle
            page.goto(url, wait_until="networkidle", timeout=20000)
            page.wait_for_timeout(1000)

            # Extract visible text from the page body
            text = _extract_page_text(page)

            # If this is an error page and we can follow links, try domain root
            if _is_error_page(text) and follow_links > 0:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                root_url = f"{parsed.scheme}://{parsed.netloc}"
                logger.info("Got error page for %s, trying domain root %s", url[:60], root_url)
                try:
                    page.goto(root_url, wait_until="networkidle", timeout=20000)
                    page.wait_for_timeout(1000)
                    root_text = _extract_page_text(page)
                    if root_text and not _is_error_page(root_text):
                        text = root_text
                        # Follow links from root instead
                        linked_texts = _follow_links(page, browser, root_url, follow_links, max_chars)
                        if linked_texts:
                            text += "\n\n## Linked Pages\n\n" + "\n\n".join(linked_texts)
                        browser.close()
                        lines = [line.strip() for line in text.splitlines() if line.strip()]
                        return "\n".join(lines)
                except Exception:
                    pass  # root fallback failed, continue with error page content

                # Root fallback also failed — return empty to avoid synthesizing from error page
                browser.close()
                logger.warning("Domain root also unreachable for %s, skipping", url[:80])
                return ""

            # Multi-page: follow relevant links
            if follow_links > 0:
                linked_texts = _follow_links(page, browser, url, follow_links, max_chars)
                if linked_texts:
                    text += "\n\n## Linked Pages\n\n" + "\n\n".join(linked_texts)

            browser.close()

            lines = [line.strip() for line in text.splitlines() if line.strip()]
            return "\n".join(lines)
    except Exception as e:
        logger.warning("Browser extraction failed for %s: %s", url[:80], e)
        return ""


def _extract_page_text(page) -> str:
    """Extract clean text from a Playwright page."""
    return page.evaluate("""
        () => {
            for (const el of document.querySelectorAll(
                'script, style, nav, footer, header, [role="navigation"]'
            )) el.remove();
            return document.body ? document.body.innerText : "";
        }
    """)


def _follow_links(page, browser, base_url: str, max_links: int, max_chars: int) -> list[str]:
    """Follow relevant links on the page and extract their content.

    Filters links to same-domain, content-like URLs, skipping nav/auxiliary pages.
    """
    import re
    from urllib.parse import urljoin, urlparse

    base_domain = urlparse(base_url).netloc

    # Extract links from the page
    links_data = page.evaluate("""
        () => {
            const links = [];
            for (const a of document.querySelectorAll('a[href]')) {
                const href = a.href;
                const text = (a.textContent || '').trim();
                // Skip empty, nav, very short links
                if (!href || !text || text.length < 10) continue;
                // Skip nav/auxiliary content
                const parent = a.closest('nav, footer, header, aside, .sidebar, .nav, .menu');
                if (parent) continue;
                links.push({href, text: text.substring(0, 200)});
            }
            return links;
        }
    """)

    # Filter to same-domain content links
    visited: set[str] = {base_url}
    selected: list[str] = []
    for link in links_data:
        href = link.get("href", "")
        if not href or href in visited:
            continue
        parsed = urlparse(href)
        # Same domain, http/https only, not fragments
        if parsed.netloc != base_domain:
            continue
        if not parsed.scheme.startswith("http"):
            continue
        # Skip non-content paths
        path_lower = parsed.path.lower()
        skip_patterns = ["/tag/", "/category/", "/author/", "/login", "/signup",
                         "/search", "/cdn-cgi", "/wp-admin", "/feed", "/rss",
                         ".pdf", ".zip", ".png", ".jpg", ".gif", ".svg"]
        if any(p in path_lower for p in skip_patterns):
            continue
        visited.add(href)
        selected.append(href)
        if len(selected) >= max_links:
            break

    # Follow each link and extract content
    results: list[str] = []
    for link_url in selected:
        try:
            new_page = browser.new_page()
            new_page.goto(link_url, wait_until="networkidle", timeout=15000)
            new_page.wait_for_timeout(500)
            text = _extract_page_text(new_page)
            new_page.close()
            if text and len(text) > 200:
                clean = "\n".join(line.strip() for line in text.splitlines() if line.strip())
                # Truncate per-page
                if len(clean) > max_chars:
                    clean = clean[:max_chars] + "\n\n[... content truncated ...]"
                results.append(f"### {link_url}\n\n{clean}")
        except Exception as e:
            logger.debug("Failed to follow link %s: %s", link_url[:80], e)

    return results
