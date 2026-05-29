"""Typed Pydantic models for node inputs/outputs.

These models document the data structures that flow between nodes.
ResearchState remains a TypedDict (LangGraph requirement), but nodes
should use these types internally to prevent string-passing bugs.

Migration path: as nodes are refactored, they should produce/consume
these models instead of raw strings.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """A single citation extracted from research findings."""

    short_id: str = Field(description="Unique identifier like src-1")
    url: str
    title: str = ""
    domain: str = ""
    tier: int = Field(default=3, ge=1, le=3)
    authority_reason: str = ""


class ResearchFinding(BaseModel):
    """Structured output from a single parallel research goal.

    Replaces the raw string that parallel_researcher_node used to return.
    Carries its own citations so they don't get lost in merge_findings_node.
    """

    goal: str = Field(description="The research goal that produced this finding")
    summary: str = Field(description="Synthesized markdown summary")
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=5.0)
    search_queries: list[str] = Field(default_factory=list)

    def to_text(self) -> str:
        """Serialize to the legacy string format for state compatibility."""
        lines = [f"### Research: {self.goal}\n", self.summary]
        return "\n\n".join(lines)


class DeliverableResult(BaseModel):
    """Structured output from the deliverable node."""

    goal: str
    text: str
    citations: list[Citation] = Field(default_factory=list)


class SourceQualityMetrics(BaseModel):
    """Aggregate source quality for a research run."""

    tier_1_count: int = 0
    tier_2_count: int = 0
    tier_3_count: int = 0
    total_sources: int = 0
    avg_tier: float = Field(default=3.0, ge=1.0, le=3.0)

    @classmethod
    def from_sources(cls, sources: dict) -> "SourceQualityMetrics":
        """Compute metrics from a sources dict (e.g. ResearchState["sources"])."""
        if not sources:
            return cls()
        tiers = []
        t1 = t2 = t3 = 0
        for src in sources.values():
            tier = src.get("tier", 3) if isinstance(src, dict) else 3
            if tier == 1:
                t1 += 1
            elif tier == 2:
                t2 += 1
            else:
                t3 += 1
            tiers.append(float(tier))
        return cls(
            tier_1_count=t1,
            tier_2_count=t2,
            tier_3_count=t3,
            total_sources=len(sources),
            avg_tier=sum(tiers) / len(tiers) if tiers else 3.0,
        )
