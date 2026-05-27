"""Graph state definitions for the deep research agent.

Defines the full ResearchState TypedDict and Pydantic models for structured
output (ADK-aligned: SearchQuery, Feedback, CitationSource, ClaimVerdict).
"""

from __future__ import annotations

import operator
from typing import Annotated, Literal, Optional, TypedDict

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# Pydantic Models (ADK-aligned structured output)
# ──────────────────────────────────────────────


class SearchQuery(BaseModel):
    """A single search query for web search."""

    search_query: str = Field(
        description="A highly specific and targeted query for web search."
    )


class Feedback(BaseModel):
    """Structured evaluation feedback, replicating ADK's Feedback schema."""

    grade: Literal["pass", "fail"] = Field(
        description="Evaluation result. 'pass' if research is sufficient, "
        "'fail' if it needs revision."
    )
    comment: str = Field(
        description="Detailed explanation of the evaluation, highlighting "
        "strengths and/or weaknesses."
    )
    follow_up_queries: list[SearchQuery] | None = Field(
        default=None,
        description="Specific follow-up search queries to fix research gaps. "
        "Should be null/empty if grade is 'pass'.",
    )


class CitationSource(BaseModel):
    """Represents a single web source with its supported claims."""

    short_id: str = Field(description="Short ID like 'src-1'")
    title: str = Field(description="Page title")
    url: str = Field(description="Full absolute URL")
    domain: str = Field(description="Domain of the source")
    tier: Literal[1, 2, 3] = Field(
        description="Source quality tier: 1=authoritative, 2=practitioner, 3=community"
    )
    authority_reason: str = Field(description="Why this source has this tier rating")
    supported_claims: list[dict] = Field(
        default_factory=list,
        description="List of {text_segment, confidence} dicts",
    )


class ClaimVerdict(BaseModel):
    """Per-claim verdict with confidence and sourcing basis."""

    text: str = Field(description="Claim text")
    confidence: Literal[1, 2, 3, 4, 5] = Field(
        description="1=speculative, 5=direct measurement"
    )
    basis: str = Field(description="Why this confidence level")
    verdict: Literal["ACCURATE", "PARTIALLY_ACCURATE", "UNSUPPORTED", "WRONG"] = Field(
        description="Verdict based on evidence"
    )


# ──────────────────────────────────────────────
# Graph State
# ──────────────────────────────────────────────


class ResearchState(TypedDict):
    """Complete state for the deep research graph.

    All nodes read from and write to this TypedDict. Fields with
    ``operator.or_`` reducers merge dicts across invocations.
    """

    # ── Phase 0-1: Planning ──
    topic: str
    """User's research topic."""
    user_feedback: Optional[str]
    """User feedback on the draft plan."""
    research_plan: Optional[str]
    """Final approved research plan with [RESEARCH]/[DELIVERABLE] tags."""
    report_sections: Optional[str]
    """Markdown outline for the final report."""
    plan_approved: bool
    """Whether the human has approved the plan."""

    # ── Phase 2: Research execution ──
    current_goal: str
    """Current research goal being processed by a parallel researcher."""
    parallel_goals: list[str]
    """All research goals extracted from the plan."""
    parallel_findings: Annotated[list, operator.add]
    """Accumulated findings from parallel researchers (reducer)."""
    section_research_findings: Optional[str]
    """Combined research findings from all phases."""
    research_iteration: int
    """Current research iteration count."""

    # ── Evaluation ──
    research_evaluation: Optional[Feedback]
    """Latest structured evaluation result."""

    # ── Citation management (ADK-aligned) ──
    url_to_short_id: Annotated[dict, operator.or_]
    """URL → short_id (src-N) mapping. Merged across calls."""
    sources: Annotated[dict, operator.or_]
    """short_id → CitationSource dict. Merged across calls."""

    # ── Phase 3: Report ──
    final_cited_report: Optional[str]
    """Report with <cite source='src-N'/> tags."""
    final_report_with_citations: Optional[str]
    """Final report with markdown citation links."""

    # ── Execution metadata ──
    messages: list
    """Conversation history for LLM calls."""
    iteration_count: int
    """Total refinement iterations performed."""
    max_iterations: int
    """Max refinement loops before forcing pass."""
    errors: list[str]
    """Accumulated non-fatal errors for graceful degradation."""
    evaluation_scores: Annotated[list, operator.add]
    """Per-iteration score breakdowns for stagnation detection.
    Each entry: {iteration, source_quality, claim_verification, completeness}."""
