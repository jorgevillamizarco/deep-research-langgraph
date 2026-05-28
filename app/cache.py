"""Cross-run goal-level cache with aggressive TTL and delta validation.

Opt-in via --cache flag. Never serves stale data silently.

Cache entry per RESEARCH goal:
  goal_hash → {findings, sources, researched_at, avg_source_tier}

TTL by source tier (aggressive, AI moves fast):
  Tier ≤1.5: 2 weeks
  Tier 1.5-2.5: 1 week
  Tier >2.5: 2 days
  Date in topic: NEVER cache

Delta check: one lightweight search for "topic + latest" validates
cache freshness before serving.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default cache DB path — next to checkpoints
CACHE_DB_PATH = Path(os.getenv("CACHE_DB_PATH", Path(os.getenv("CHECKPOINT_DB_PATH", "checkpoints.db")).parent / "research_cache.db"))


def _get_conn() -> sqlite3.Connection:
    """Get or create cache DB connection."""
    CACHE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CACHE_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS goal_cache (
            goal_hash TEXT PRIMARY KEY,
            goal_text TEXT NOT NULL,
            findings TEXT NOT NULL,
            sources_json TEXT DEFAULT '{}',
            researched_at TEXT NOT NULL,
            avg_source_tier REAL DEFAULT 3.0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_researched_at ON goal_cache(researched_at)")
    conn.commit()
    return conn


def _normalize(text: str) -> str:
    """Aggressively normalize goal text for comparison across LLM runs."""
    import re
    t = text.strip().lower()
    t = re.sub(r'\*+', '', t)
    t = re.sub(r'^\d+[\.\)]\s*', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _key_phrase(text: str, words: int = 8) -> str:
    """Extract first N words as the cache key — ignores LLM elaboration."""
    return ' '.join(_normalize(text).split()[:words])


def _hash_goal(goal_text: str) -> str:
    """Hash the key phrase (first 8 words) for cache lookup."""
    return hashlib.sha256(_key_phrase(goal_text).encode()).hexdigest()[:16]


def _similarity(a: str, b: str) -> float:
    """Text similarity ratio for fuzzy goal matching."""
    from difflib import SequenceMatcher
    return SequenceMatcher(None, _key_phrase(a), _key_phrase(b)).ratio()


def _find_cached_goal(goal_text: str) -> tuple[str, tuple] | None:
    """Find a cached goal by exact hash or fuzzy match (similarity > 0.7)."""
    goal_hash = _hash_goal(goal_text)
    conn = _get_conn()
    
    # Exact match first
    row = conn.execute(
        "SELECT goal_hash, goal_text, findings, sources_json, researched_at, avg_source_tier "
        "FROM goal_cache WHERE goal_hash = ?", (goal_hash,)
    ).fetchone()
    if row:
        return ("exact", row)
    
    # Fuzzy match
    all_rows = conn.execute(
        "SELECT goal_hash, goal_text, findings, sources_json, researched_at, avg_source_tier "
        "FROM goal_cache"
    ).fetchall()
    
    best = None
    best_sim = 0.0
    for row in all_rows:
        sim = _similarity(goal_text, row[1])
        if sim > best_sim:
            best_sim = sim
            best = row
    
    if best and best_sim > 0.7:
        return ("fuzzy", best)
    
    return None


def _ttl_seconds(avg_tier: float) -> int:
    """Aggressive TTL by source tier."""
    if avg_tier <= 1.5:
        return 14 * 24 * 3600   # 2 weeks
    elif avg_tier <= 2.5:
        return 7 * 24 * 3600    # 1 week
    else:
        return 2 * 24 * 3600    # 2 days


def _topic_is_date_bound(topic: str) -> bool:
    """True if topic contains a year — never cache date-bound research."""
    import re
    return bool(re.search(r'\b(20\d\d)\b', topic))


def _delta_check(topic: str, goal_text: str, cached_sources: dict) -> bool:
    """Run one lightweight search to validate cache freshness.
    
    Returns True if cache appears fresh (no substantially new results).
    Returns False if new/more recent results found → should re-research.
    """
    try:
        from app.tools.search import get_search_tool
        search = get_search_tool()
        query = f"{topic} latest"
        results = search.invoke({"query": query, "max_results": 3})
        
        # Check if any results are from new domains not in cached sources
        cached_urls = set()
        for src in cached_sources.values() if isinstance(cached_sources, dict) else []:
            if isinstance(src, dict):
                cached_urls.add(src.get("url", ""))
        
        new_domains = 0
        if hasattr(results, 'results'):
            for r in results.results[:3]:
                url = getattr(r, 'url', '') or getattr(r, 'link', '')
                if url and url not in cached_urls:
                    new_domains += 1
        
        # If 2+ results are from new domains, cache is stale
        return new_domains < 2
    except Exception as e:
        logger.warning("Delta check failed: %s — assuming stale", e)
        return False


def get_cached_goal(goal_text: str, topic: str) -> dict | None:
    """Check cache for a goal. Returns findings dict or None.
    
    Uses exact hash match first, then fuzzy text matching (>0.7 similarity).
    Validates TTL and runs delta check before serving.
    Always returns None (fresh research) for date-bound topics.
    """
    if _topic_is_date_bound(topic):
        return None
    
    result = _find_cached_goal(goal_text)
    if not result:
        return None
    
    match_type, row = result
    goal_hash_db, goal_text_db, findings, sources_json, researched_at, avg_tier = row
    
    # Check TTL
    try:
        researched_dt = datetime.datetime.fromisoformat(researched_at)
        age_seconds = (datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - researched_dt).total_seconds()
    except (ValueError, TypeError):
        age_seconds = float('inf')
    
    if age_seconds > _ttl_seconds(avg_tier):
        logger.info("Cache expired for goal (age=%ds, ttl=%ds): %s",
                    int(age_seconds), _ttl_seconds(avg_tier), goal_text[:60])
        return None
    
    # Delta check — skip for very fresh cache (< 1 hour)
    sources = {}
    if age_seconds < 3600:
        logger.info("Cache fresh (age=%ds, delta skipped): %s", int(age_seconds), goal_text[:60])
    else:
        try:
            sources = json.loads(sources_json) if sources_json else {}
        except json.JSONDecodeError:
            sources = {}
        if not _delta_check(topic, goal_text, sources):
            logger.info("Delta check FAILED for goal: %s", goal_text[:60])
            return None

    match_label = "exact" if match_type == "exact" else f"fuzzy (sim={_similarity(goal_text, goal_text_db):.2f})"
    logger.info("Cache HIT (%s) for goal (age=%ds): %s", match_label, int(age_seconds), goal_text[:60])
    return {
        "findings": findings,
        "sources": sources,
        "researched_at": researched_at,
        "avg_source_tier": avg_tier,
    }


def cache_goal(goal_text: str, findings: str, sources: dict, avg_tier: float = 3.0) -> None:
    """Store a goal's findings in cache. Overwrites existing entry."""
    if _topic_is_date_bound(""):  # Don't cache if date-bound — checked at get time
        return
    
    goal_hash = _hash_goal(goal_text)
    conn = _get_conn()
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat()
    sources_json = json.dumps(sources) if sources else "{}"
    
    conn.execute(
        "INSERT OR REPLACE INTO goal_cache (goal_hash, goal_text, findings, sources_json, researched_at, avg_source_tier) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (goal_hash, goal_text, findings, sources_json, now, avg_tier)
    )
    conn.commit()
    logger.info("Cached goal: %s (tier=%.1f)", goal_text[:60], avg_tier)


def compute_avg_tier(sources: dict) -> float:
    """Compute average source tier from sources dict."""
    if not sources:
        return 3.0
    tiers = []
    for src in sources.values():
        if isinstance(src, dict):
            tier = src.get("tier", 3)
            if isinstance(tier, (int, float)):
                tiers.append(float(tier))
    return sum(tiers) / len(tiers) if tiers else 3.0
