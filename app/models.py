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


# ── Type-safe state accessors ──
# Convert between string-based LangGraph state and typed Pydantic models
# at node boundaries. Avoids regex parsing for citation/confidence extraction.


def findings_from_state(state: dict) -> list[ResearchFinding]:
    """Extract typed ResearchFindings from state's serialized findings.

    Reads section_research_findings (combined string) and splits into
    per-goal sections. Returns empty list if no findings exist.

    This is the typed entry point — use instead of raw string parsing.
    """
    text = state.get("section_research_findings", "") or ""
    if not text.strip():
        # Fall back to parallel_findings if section hasn't been populated yet
        parallel = state.get("parallel_findings", [])
        if parallel:
            text = "\n\n---\n\n".join(str(f) for f in parallel)
    if not text.strip():
        return []

    findings: list[ResearchFinding] = []
    # Split on markdown section boundaries: "### Research: " or "---"
    import re
    sections = re.split(r"\n(?=### Research:|\n---\n)", text)
    for section in sections:
        section = section.strip()
        if not section:
            continue
        # Extract citations from the finding text
        citations = _extract_typed_citations(section, state.get("sources", {}))
        findings.append(ResearchFinding(
            goal_text=section.split("\n")[0].replace("### Research: ", "").strip()[:100],
            summary=section,
            citations=citations,
        ))
    return findings


def findings_to_state(findings: list[ResearchFinding]) -> dict:
    """Serialize typed findings back to state-compatible format.

    Returns a dict with 'section_research_findings' key suitable for
    merging into the LangGraph state.
    """
    text = "\n\n---\n\n".join(f.to_markdown() for f in findings)
    # Also extract all citations for the sources dict
    sources: dict[str, dict] = {}
    url_map: dict[str, str] = {}
    for i, finding in enumerate(findings):
        for j, c in enumerate(finding.citations):
            sid = c.short_id or f"src-{len(sources) + 1}"
            sources[sid] = {
                "short_id": sid, "url": c.url, "title": c.title, "tier": c.tier,
            }
            url_map[c.url] = sid
    return {
        "section_research_findings": text,
        "sources": sources,
        "url_to_short_id": url_map,
    }


def get_typed_sources(state: dict) -> dict[str, Citation]:
    """Get typed Citation objects from state's sources dict."""
    raw_sources = state.get("sources", {}) or {}
    typed: dict[str, Citation] = {}
    for sid, src in raw_sources.items():
        typed[sid] = Citation(
            short_id=sid,
            url=src.get("url", "") if isinstance(src, dict) else "",
            title=src.get("title", "") if isinstance(src, dict) else "",
            tier=src.get("tier", 3) if isinstance(src, dict) else 3,
        )
    return typed


def _extract_typed_citations(text: str, sources: dict) -> list[Citation]:
    """Extract Citation objects from finding text using state sources for metadata."""
    import re
    citations: list[Citation] = []
    seen_urls: set[str] = set()
    # Find markdown links: [Title](URL)
    for match in re.finditer(r"\[([^\]]+)\]\((https?://[^\)]+)\)", text):
        url = match.group(2)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        title = match.group(1)
        # Look up tier from existing sources
        tier = 3
        for sid, src in sources.items():
            if isinstance(src, dict) and src.get("url") == url:
                tier = src.get("tier", 3)
                break
        citations.append(Citation(
            short_id=f"src-{len(citations) + 1}",
            url=url, title=title, tier=tier,
        ))
    return citations
