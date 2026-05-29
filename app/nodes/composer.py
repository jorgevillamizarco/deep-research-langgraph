"""Composer node — final report synthesis with structured citations.

Replicates ADK's ``report_composer`` + ``citation_replacement_callback``.

Two passes:
1. LLM writes the report with ``<cite source="src-N"/>`` tags.
2. Regex replacement converts tags to markdown links using the sources dict.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import config
from app.state import ResearchState
from app.tools.citations import replace_citation_tags

logger = logging.getLogger(__name__)


def _get_llm() -> Any:
    from app.tokens import get_llm
    return get_llm(model=config.worker_model, temperature=0.2,
                   api_key=config.worker_api_key or None,
                   base_url=config.worker_api_base or None)


def _serialize_sources(sources: dict) -> str:
    """Serialize sources to a compact JSON string for the LLM prompt.

    Only includes fields the LLM needs for citation (short_id, title, url, tier).
    Drops verbose metadata (authority_reason, supported_claims) to reduce
    prompt bloat. With 40+ sources, this can save ~5-10K tokens.
    """
    essential_keys = {"short_id", "title", "url", "domain", "tier"}
    compact = {}
    for sid, src in sources.items():
        compact[sid] = {
            k: str(v) if not isinstance(v, (str, int, float, bool, list, dict, type(None))) else v
            for k, v in src.items()
            if k in essential_keys
        }
    return json.dumps(compact, indent=2)


def composer_node(state: ResearchState) -> dict:
    """Transform research findings and section outline into a final cited report.

    Pass 1: LLM generates the report using ``<cite source="src-N"/>`` tags.
    Pass 2: Replace tags with markdown links.
    """
    findings = state.get("section_research_findings", "")
    plan = state.get("research_plan", "")
    sections = state.get("report_sections", "")
    sources = state.get("sources", {})
    evaluations = state.get("research_evaluation")
    topic = state.get("topic", "")
    errors = state.get("errors", [])
    scores = state.get("evaluation_scores", [])

    if not findings:
        return {
            "final_cited_report": "No research findings were generated.",
            "final_report_with_citations": "No research findings were generated.",
        }

    depth = state.get("depth", "standard")

    if depth == "brief":
        # Brief mode: executive summary only, no full report generation
        brief_prompt = f"""You are a research summarizer. Produce a 2-3 paragraph executive summary.

Research Topic: {topic}

Findings:
{findings[:15000]}

Write a concise executive summary (2-3 paragraphs, ~300-500 words). Include:
- The key finding or answer
- 2-3 supporting data points with citations as [Title](URL)
- Overall confidence assessment (high/moderate/low)
- One caveat or limitation

Be direct. No section headers, no methodology, no source quality assessment.
Just the summary."""
        llm = _get_llm()
        response = llm.invoke([
            SystemMessage(content="You write concise research summaries."),
            HumanMessage(content=brief_prompt),
        ])
        summary = response.content.strip()
        return {
            "final_cited_report": summary,
            "final_report_with_citations": summary,
            **llm.token_delta(),
        }

    # Standard mode: full structured report

    llm = _get_llm()
    sources_json = _serialize_sources(sources)

    eval_note = ""
    if evaluations:
        eval_note = f"\nThe research was evaluated as: {evaluations.grade.upper()}\nEvaluator comment: {evaluations.comment}\n"

    errors_note = ""
    if errors:
        error_list = "\n".join(f"  - {e}" for e in errors)
        errors_note = f"\nNON-FATAL ERRORS encountered during research (note in Methodology):\n{error_list}\n"

    cache_note = ""
    cached_count = state.get("cached_goal_count", 0)
    if cached_count:
        cache_note = f"\n{cached_count} research goal(s) were served from cross-run cache (delta-validated, within TTL). Note in Methodology.\n"

    scores_note = ""
    if scores:
        last = scores[-1]
        scores_note = (
            f"\nFINAL EVALUATION SCORES: source_quality={last.get('source_quality','?')}/5, "
            f"claim_verification={last.get('claim_verification','?')}/5, "
            f"completeness={last.get('completeness','?')}/5 "
            f"(after {len(scores)} iteration(s))\n"
        )

    system_prompt = f"""You are a professional research report composer. Transform the provided data into a polished, meticulously cited research report.

    CRITICAL CITATION SYSTEM:
    To cite a source, you MUST insert a special citation tag directly after the claim it supports.
    The ONLY correct format is: <cite source="src-ID_NUMBER" />

    INPUTS:
    - Research Plan: {plan}
    - Research Findings: {findings}
    - Citation Sources (JSON): {sources_json}
    - Report Structure: {sections}
    {eval_note}
    {scores_note}
    {errors_note}
    {cache_note}
    - Topic: {topic}

    SOURCE QUALITY TIERS (for internal quality weighting — do NOT annotate citations with tiers):
      Tier 1 — academic papers, official docs, government (.gov, .edu, arxiv, IEEE)
      Tier 2 — engineering blogs, industry publications, GitHub repos
      Tier 3 — community forums, news, vendor content
    Use the tier metadata to:
    - Prefer Tier 1/2 sources for key claims
    - Note when only Tier 3 sources support an important claim
    - Build the Source Quality Assessment section (aggregate counts, not per-citation labels)
    Do NOT include [T1]/[T2]/[T3] labels in citation text — the domain speaks for itself.

    PER-CLAIM CONFIDENCE: The research findings include [CONFIDENCE:N/5] tags on claims.
    PRESERVE these confidence levels in your report. When a claim has borderline or low
    confidence (≤3), explicitly note the uncertainty: "Evidence suggests..." or
    "Preliminary data indicates..." rather than stating it as settled fact.

    REPORT STRUCTURE (use the provided outline below as your primary section list):
    # {topic}: Deep Research Report
    ## Executive Summary
    [3-5 paragraphs. Standalone — readable without reading the full report.
     Include overall confidence assessment: what's well-established vs speculative.]

    {sections}

    ## Cross-Cutting Themes
    [Patterns across sections. Note any contradictions explicitly — flag them as
     "CONTRADICTION:" followed by the conflicting claims and their sources.]

    ## Gaps & Uncertainties
    [What's missing or unclear. List claims with confidence ≤2 as needing further investigation.]

    ## Source Quality Assessment
    [Brief assessment of evidence quality: how many Tier 1/2/3 sources, any reliance on
     low-quality sources for key claims, overall strength of the evidence base.]

    ## Methodology
    [Brief note on how the research was conducted: web search, iterative refinement, etc.
     If NON-FATAL ERRORS were reported, note them here. If scores improved across iterations,
     mention the refinement process. If goals were served from cross-run cache, note it here.]

    COMPOSITION RULES:
    1. Every factual claim must have an inline citation tag.
    2. All content must be inline — never reference external files.
    3. Flag contradictions between different findings explicitly with "CONTRADICTION:" prefix.
    4. Preserve specific numbers, dates, and technical details.
    5. Do NOT include a "References" or "Sources" section — all citations are inline.
    6. The Executive Summary must be completely standalone.
    7. NEVER state a low-confidence claim (≤3) as fact — hedge appropriately.
    8. Prefer Tier 1 sources for key claims; note when only Tier 3 sources are available."""

    try:
        print("  📄 Generating report...", flush=True)
        response_parts = []
        for chunk in llm.stream([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Produce the final research report for: {topic}"),
        ]):
            text = chunk.content if hasattr(chunk, "content") else str(chunk)
            response_parts.append(text)
            print(text, end="", flush=True)
        report_with_tags = "".join(response_parts).strip()
        print(flush=True)  # final newline

    except Exception as e:
        logger.error("Composer LLM call failed: %s", e)
        return {
            "final_cited_report": f"Report generation failed: {e}",
            "final_report_with_citations": f"Report generation failed: {e}",
            "errors": state.get("errors", []) + [f"Composer error: {e}"],
        }

    # Pass 2: Replace citation tags with markdown links
    report_with_markdown = replace_citation_tags(report_with_tags, sources)

    print(f"  📄 Report generated — {len(report_with_markdown):,} chars", flush=True)

    # ── State pruning: cap accumulators to prevent O(N²) checkpoint bloat ──
    # Finding: LangGraph checkpoints grow quadratically with history length.
    # A 200-turn agent can reach 5.3 GB. Capping lists prevents unbounded growth.
    max_errors = 50
    max_scores = 5
    max_messages = 20
    max_findings = 20

    pruned_errors = state.get("errors", [])[-max_errors:]
    pruned_scores = state.get("evaluation_scores", [])[-max_scores:]
    pruned_messages = state.get("messages", [])[-max_messages:]
    pruned_findings = state.get("parallel_findings", [])[-max_findings:]

    if len(state.get("errors", [])) > max_errors:
        logger.info("State pruned: errors %d→%d", len(state.get("errors", [])), max_errors)
    if len(state.get("messages", [])) > max_messages:
        logger.info("State pruned: messages %d→%d", len(state.get("messages", [])), max_messages)

    return {
        "final_cited_report": report_with_tags,
        "final_report_with_citations": report_with_markdown,
        "messages": pruned_messages,
        "errors": pruned_errors,
        "evaluation_scores": pruned_scores,
        "parallel_findings": pruned_findings,
        **llm.token_delta(),
    }
