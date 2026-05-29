"""Cross-run goal-level cache — DEPRECATED.

The cache system has been deprecated (May 2026). It added 300+ lines of complexity
for marginal benefit due to LLM non-determinism producing low hit rates. All
functions are now no-ops that log a deprecation warning.

For history, the original implementation supported:
- Goal-level caching with SHA-256 key hashing
- Fuzzy text matching (SequenceMatcher > 0.7)
- Tier-based TTL (2 days — 2 weeks)
- Delta validation via lightweight search
- Date-bound topic exclusion

Removal plan: This file will be deleted in a future release.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_deprecation_warned = False


def _warn() -> None:
    global _deprecation_warned
    if not _deprecation_warned:
        logger.warning(
            "Cross-run cache is deprecated and will be removed in a future release. "
            "Fresh research with fast models is preferred."
        )
        _deprecation_warned = True


def get_cached_goal(goal_text: str, topic: str) -> None:
    """DEPRECATED. Always returns None."""
    _warn()
    return None


def cache_goal(goal_text: str, findings: str, sources: dict, avg_tier: float = 3.0) -> None:
    """DEPRECATED. No-op."""
    _warn()
    return None


def compute_avg_tier(sources: dict) -> float:
    """DEPRECATED. Always returns 3.0 (neutral tier)."""
    _warn()
    return 3.0
