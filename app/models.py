"""Typed Pydantic models for node outputs and intermediate research data.

These models replace the previous "strings everywhere" architecture with
type-safe structures that carry citations, confidence scores, and metadata
natively instead of relying on regex parsing.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """A single cited source with quality metadata."""

    short_id: str = Field(description="Unique identifier (e.g. src-1)")
    url: str = Field(description="Source URL")
    title: str = Field(default="", description="Source title")
    tier: int = Field(default=3, ge=1, le=3, description="Source quality tier (1=best, 3=weakest)")
    authority_reason: str = Field(default="", description="Why this tier was assigned")
    supported_claims: list[str] = Field(default_factory=list, description="Claims this source supports")


class ConfidenceTag(BaseModel):
    """Per-claim confidence annotation from researcher nodes."""

    score: int = Field(ge=1, le=5, description="Confidence level (5=definite, 1=guess)")
    claim_text: str = Field(default="", description="The claim being tagged")


class ResearchFinding(BaseModel):
    """Output from a single research goal execution.

    Carries structured data (citations, confidence) instead of raw markdown,
    enabling type-safe processing in downstream nodes.
    """

    goal_text: str = Field(description="The research goal this finding addresses")
    summary: str = Field(description="Synthesized markdown summary")
    citations: list[Citation] = Field(default_factory=list, description="Sources cited")
    confidence_tags: list[ConfidenceTag] = Field(default_factory=list, description="Per-claim confidence annotations")
    search_queries: list[str] = Field(default_factory=list, description="Queries that generated this finding")
    word_count: int = Field(default=0, description="Approximate word count of the summary")

    def to_markdown(self) -> str:
        """Serialize to the markdown format expected by deliverable/composer nodes."""
        lines = [f"### Research: {self.goal_text}", "", self.summary, ""]
        if self.citations:
            lines.append("**Sources:**")
            for c in self.citations:
                lines.append(f"- [{c.title}]({c.url}) — Tier {c.tier}")
            lines.append("")
        return "\n".join(lines)


class Deliverable(BaseModel):
    """A single deliverable artifact produced in Phase 2."""

    goal_text: str = Field(description="The deliverable goal")
    content: str = Field(description="The generated deliverable text")
    citations: list[Citation] = Field(default_factory=list, description="Sources cited in this deliverable")

    def to_markdown(self) -> str:
        """Serialize to markdown format."""
        return f"### Deliverable: {self.goal_text}\n\n{self.content.strip()}\n"


class ResearchOutput(BaseModel):
    """Combined output from the full research pipeline.

    Replaces the raw string concatenation in section_research_findings
    with a structured representation that nodes can query and modify safely.
    """

    findings: list[ResearchFinding] = Field(default_factory=list, description="Phase 1 research findings")
    deliverables: list[Deliverable] = Field(default_factory=list, description="Phase 2 deliverable artifacts")
    sources: dict[str, Citation] = Field(default_factory=dict, description="All sources keyed by short_id")
    url_to_short_id: dict[str, str] = Field(default_factory=dict, description="URL → short_id mapping")

    def to_composer_input(self) -> str:
        """Convert to the string format expected by the composer node."""
        parts = ["# Research Findings", "", "## Research Summaries", ""]
        for f in self.findings:
            parts.append(f.to_markdown())
        if self.deliverables:
            parts.extend(["", "## Deliverables", ""])
            for d in self.deliverables:
                parts.append(d.to_markdown())
        return "\n".join(parts)

    @property
    def total_citations(self) -> int:
        """Total unique citations across all findings and deliverables."""
        return len(self.sources)

    @property
    def avg_confidence(self) -> float:
        """Average confidence score across all findings."""
        scores: list[int] = []
        for f in self.findings:
            scores.extend([t.score for t in f.confidence_tags])
        return sum(scores) / len(scores) if scores else 0.0
