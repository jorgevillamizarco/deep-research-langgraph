"""Citation management — ADK-aligned source extraction and formatting.

Replicates the ADK ``collect_research_sources_callback`` and
``citation_replacement_callback`` functionality.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Regex to find markdown links in text: [title](url)
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
# Regex to find raw URLs
_RAW_URL_RE = re.compile(r"https?://[^\s)]+")


def extract_citations_from_content(content: str, existing_id_counter: int = 0) -> tuple[dict[str, Any], dict[str, str]]:
    """Extract URL-based citations from LLM-generated content.

    Parses markdown links and raw URLs, builds:
    - sources: short_id → {short_id, title, url, domain, tier, authority_reason, supported_claims}
    - url_to_short_id: url → short_id

    This is the LangGraph equivalent of ADK's ``collect_research_sources_callback``.

    Args:
        content: Text content (findings, report) to scan for citations.
        existing_id_counter: Starting counter for ``src-N`` IDs.

    Returns:
        Tuple of (sources_dict, url_to_short_id_dict).
    """
    sources: dict[str, Any] = {}
    url_to_short_id: dict[str, str] = {}
    id_counter = existing_id_counter

    seen_urls: set[str] = set()

    # 1. Extract markdown links
    for match in _MD_LINK_RE.finditer(content):
        title = match.group(1).strip()
        url = match.group(2).strip()
        if url in seen_urls:
            continue
        seen_urls.add(url)
        id_counter += 1
        short_id = f"src-{id_counter}"
        url_to_short_id[url] = short_id
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        sources[short_id] = {
            "short_id": short_id,
            "title": title or domain,
            "url": url,
            "domain": domain,
            "tier": 3,  # Default tier, will be refined by critic
            "authority_reason": "Extracted from research findings",
            "supported_claims": [],
        }

    # 2. Extract raw URLs not already captured in markdown links
    for match in _RAW_URL_RE.finditer(content):
        url = match.group(0).rstrip(".,;:!?)")
        if url in seen_urls:
            continue
        # Skip obvious non-content URLs (e.g. images)
        if any(ext in url for ext in (".png", ".jpg", ".gif", ".svg")):
            continue
        seen_urls.add(url)
        id_counter += 1
        short_id = f"src-{id_counter}"
        url_to_short_id[url] = short_id
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        sources[short_id] = {
            "short_id": short_id,
            "title": domain,
            "url": url,
            "domain": domain,
            "tier": 3,
            "authority_reason": "Extracted as raw URL from research content",
            "supported_claims": [],
        }

    return sources, url_to_short_id


def replace_citation_tags(text: str, sources: dict[str, Any]) -> str:
    """Replace ``<cite source="src-N"/>`` tags with markdown links.

    This is the LangGraph equivalent of ADK's ``citation_replacement_callback``.

    Args:
        text: Report text containing ``<cite source="src-N"/>`` tags.
        sources: Dict mapping short_id to source info with ``title`` and ``url``.

    Returns:
        Text with citation tags replaced by markdown links.
    """
    def _replacer(match: re.Match) -> str:
        short_id = match.group(1)
        source = sources.get(short_id)
        if not source:
            logger.warning("Unknown citation tag: %s", match.group(0))
            return ""
        title = source.get("title", source.get("domain", short_id))
        url = source.get("url", "")
        return f" [{title}]({url})"

    result = re.sub(
        r"""<cite\s+source\s*=\s*["']?\s*(src-\d+)\s*["']?\s*/>""",
        _replacer,
        text,
    )
    # Fix spacing around punctuation
    result = re.sub(r"\s+([.,;:!?)])", r"\1", result)
    return result


def annotate_source_tier(source: dict[str, Any], domain: str | None = None) -> dict[str, Any]:
    """Heuristically assign a source quality tier based on domain.

    Tier 1: arxiv, academic journals, gov/edu, official docs
    Tier 2: engineering blogs, industry publications
    Tier 3: community, news, vendor content
    """
    domain = domain or source.get("domain", "")
    source["tier"] = 3  # default

    tier1_domains = [
        "arxiv.org", "ieee.org", "acm.org", "sciencedirect.com",
        "springer.com", "nature.com", "science.org", "nih.gov",
        ".gov", ".edu", "ietf.org", "rfc-editor.org",
        "w3.org", "docs.", "spec.", "api.",
    ]
    tier2_domains = [
        "blog.", "eng.", "engineering.", "medium.com/",
        "lwn.net", "theregister.com", "infoq.com",
        "github.com", "gitlab.com", "pypi.org", "npmjs.com",
        "stackoverflow.com", "stackexchange.com",
    ]

    lower_domain = domain.lower()
    for t1 in tier1_domains:
        if t1 in lower_domain:
            source["tier"] = 1
            source["authority_reason"] = f"Authoritative domain: {domain}"
            return source

    for t2 in tier2_domains:
        if t2 in lower_domain:
            source["tier"] = 2
            source["authority_reason"] = f"Practitioner domain: {domain}"
            return source

    source["authority_reason"] = f"Community/news domain: {domain}"
    return source
