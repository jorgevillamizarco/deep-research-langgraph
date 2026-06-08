"""Composer node — final report synthesis with structured citations.

Replicates ADK's ``report_composer`` + ``citation_replacement_callback``.

Two passes:
1. LLM writes the report with ``<cite source="src-N"/>`` tags.
2. Regex replacement converts tags to markdown links using the sources dict.
"""

from __future__ import annotations

import json
import logging
import re
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
                   base_url=config.worker_api_base or None,
                   node_name="composer")


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


def get_template_block_config(report_blueprint: dict | None) -> list[str]:
    """Return deterministic block defaults for each report template."""
    template = (report_blueprint or {}).get("template", "generic_research_report")
    blocks_by_template = {
        "generic_research_report": [
            "answer_first_summary",
            "open_questions",
        ],
        "decision_memo": [
            "answer_first_summary",
            "what_is_being_decided",
            "key_facts_table",
            "scenario_table",
            "recommendation_block",
            "open_questions",
        ],
        "retail_investor_memo": [
            "answer_first_summary",
            "what_is_being_decided",
            "key_facts_table",
            "economics_or_mechanics",
            "scenario_table",
            "risk_table",
            "decision_checklist",
            "recommendation_block",
            "open_questions",
        ],
        "architecture_review": [
            "answer_first_summary",
            "what_is_being_decided",
            "economics_or_mechanics",
            "risk_table",
            "recommendation_block",
            "open_questions",
        ],
        "compare_and_recommend": [
            "answer_first_summary",
            "key_facts_table",
            "scenario_table",
            "recommendation_block",
            "open_questions",
        ],
        "legal_policy_brief": [
            "answer_first_summary",
            "timeline",
            "recommendation_block",
            "open_questions",
        ],
    }
    return blocks_by_template.get(template, blocks_by_template["generic_research_report"])


def _extract_claims_from_report(report: str, sources: dict) -> list[dict]:
    """Extract structured claims from the report body for the Major Claims table.

    Scans for sentences containing [src-N] citations and creates claim objects
    with confidence derived from source tier.
    """
    claims: list[dict] = []
    seen_texts: set[str] = set()

    for match in re.finditer(r"(?:\[src-(\d+)\]|<cite\s+(?:source=\"src-(\d+)\"|src=\"(\d+)\"))", report):
        src_num = match.group(1) or match.group(2) or match.group(3)
        src_id = f"src-{src_num}"
        src = sources.get(src_id, {})
        tier = src.get("tier", 3)
        if isinstance(tier, str):
            try:
                tier = int(tier)
            except (ValueError, TypeError):
                tier = 3
        confidence = 5 if tier == 1 else 4 if tier == 2 else 3

        pos = match.start()
        before = report.rfind(". ", 0, pos)
        before = report.rfind("! ", 0, pos) if report.rfind("! ", 0, pos) > before else before
        before = report.rfind("? ", 0, pos) if report.rfind("? ", 0, pos) > before else before
        before = report.rfind(".\n", 0, pos) if report.rfind(".\n", 0, pos) > before else before
        start = before + 2 if before >= 0 else max(0, pos - 200)

        after = report.find(". ", pos)
        after_alt = report.find(".\n", pos)
        if after_alt >= 0 and (after < 0 or after_alt < after):
            after = after_alt
        end = after + 1 if after >= 0 else min(len(report), pos + 200)

        claim_text = report[start:end].strip()
        claim_text = re.sub(r"\s+", " ", claim_text)[:200]

        if claim_text not in seen_texts:
            seen_texts.add(claim_text)
            claims.append({
                "claim_id": f"claim-{len(claims) + 1}",
                "text": claim_text,
                "confidence": confidence,
                "support_source_ids": [src_id],
                "evidence_strength": "high" if confidence >= 4 else "medium" if confidence == 3 else "low",
            })

    return claims


def build_evidence_appendix(sources: dict, evidence_claims: list[dict] | None, evidence_gaps: list[dict] | None) -> str:
    evidence_claims = evidence_claims or []
    evidence_gaps = evidence_gaps or []
    if not sources and not evidence_claims and not evidence_gaps:
        return ""

    lines = [
        "## Evidence Appendix",
        "",
        "### Source Register",
        "| Source | Tier | Type | Used for | Notes |",
        "|---|---:|---|---|---|",
    ]
    for sid, src in sorted(sources.items()):
        lines.append(
            "| {source} | {tier} | {source_type} | {used_for} | {notes} |".format(
                source=f"{sid}: [{src.get('title', sid)}]({src.get('url', '')})",
                tier=src.get("tier", "?"),
                source_type=src.get("source_type", "unknown"),
                used_for=", ".join(src.get("used_for_claims", [])) or "—",
                notes=src.get("authority_reason", "") or "—",
            )
        )

    lines.extend([
        "",
        "### Major Claims",
        "| Claim | Confidence | Evidence | Caveat |",
        "|---|---:|---|---|",
    ])
    for claim in evidence_claims:
        evidence_links = ", ".join(claim.get("support_source_ids", [])) or "—"
        caveat = claim.get("evidence_strength", "")
        lines.append(
            f"| {claim.get('text', '')} | {claim.get('confidence', '?')} | {evidence_links} | {caveat or '—'} |"
        )

    lines.extend([
        "",
        "### Missing Evidence",
        "| Gap | Why it matters | Impact |",
        "|---|---|---|",
    ])
    for gap in evidence_gaps:
        lines.append(
            f"| {gap.get('description', '')} | {gap.get('why_it_matters', '') or '—'} | {gap.get('impact_on_conclusion', '') or '—'} |"
        )

    return "\n".join(lines)


def _compose_section_outline(topic: str, report_blueprint: dict | None, sections: str) -> str:
    """Build the section guidance passed into the composer prompt."""
    blueprint = report_blueprint or {}
    template = blueprint.get("template", "generic_research_report")
    block_config = ", ".join(get_template_block_config(blueprint))
    section_lines = [
        f"# {topic}: Deep Research Report",
        "## Executive Summary",
        "[3-5 paragraphs. Standalone — readable without reading the full report.",
        " Include overall confidence assessment: what's well-established vs speculative.]",
        "",
    ]
    if sections.strip():
        section_lines.append(sections.strip())
    section_lines.extend([
        "",
        "## Cross-Cutting Themes",
        "[Patterns across sections. Note any contradictions explicitly — flag them as",
        ' "CONTRADICTION:" followed by the conflicting claims and their sources.]',
        "",
        "## Gaps & Uncertainties",
        "[What's missing or unclear. List claims with confidence ≤2 as needing further investigation.]",
        "",
        "## Source Quality Assessment",
        "[Brief assessment of evidence quality: how many Tier 1/2/3 sources, any reliance on",
        " low-quality sources for key claims, overall strength of the evidence base.]",
        "",
        "## Methodology",
        "[Brief note on how the research was conducted: web search, iterative refinement, etc.]",
        "",
        f"Template: {template}",
        f"Preferred report blocks: {block_config}",
    ])
    return "\n".join(section_lines)


def composer_node(state: ResearchState) -> dict:
    """Transform research findings and section outline into a final cited report.

    Pass 1: LLM generates the report using ``<cite source="src-N"/>`` tags.
    Pass 2: Replace tags with markdown links.
    """
    findings = state.get("section_research_findings", "")
    plan = state.get("research_plan", "")
    sections = state.get("report_sections") or ""
    report_blueprint = state.get("report_blueprint") or {}
    sources = state.get("sources", {})
    evidence_claims = state.get("evidence_claims", [])
    evidence_gaps = state.get("evidence_gaps", [])
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

    scores_note = ""
    if scores:
        last = scores[-1]
        scores_note = (
            f"\nFINAL EVALUATION SCORES: source_quality={last.get('source_quality','?')}/5, "
            f"claim_verification={last.get('claim_verification','?')}/5, "
            f"completeness={last.get('completeness','?')}/5 "
            f"(after {len(scores)} iteration(s))\n"
        )

    section_outline = _compose_section_outline(topic, report_blueprint, sections)

    system_prompt = f"""You are a professional research report composer. Transform the provided data into a polished, meticulously cited research report.

    CRITICAL CITATION SYSTEM:
    To cite a source, you MUST insert a special citation tag directly after the claim it supports.
    The ONLY correct format is: <cite source="src-ID_NUMBER" />

    INPUTS:
    - Research Plan: {plan}
    - Research Findings: {findings}
    - Citation Sources (JSON): {sources_json}
    - Report Structure: {section_outline}
    {eval_note}
    {scores_note}
    {errors_note}
    - Topic: {topic}

    SOURCE QUALITY TIERS (for internal quality weighting — do NOT annotate citations with tiers):
      Tier 1 — academic papers, official docs, government (.gov, .edu, arxiv, IEEE)
      Tier 2 — engineering blogs, industry publications
      Tier 3 — community, news, vendor content
    Use the tier metadata to:
    - Prefer Tier 1/2 sources for key claims
    - Note when only Tier 3 sources support an important claim
    - Build the Source Quality Assessment section (aggregate counts, not per-citation labels)
    Do NOT include [T1]/[T2]/[T3] labels in citation text — the domain speaks for itself.

    PER-CLAIM CONFIDENCE: The research findings include [CONFIDENCE:N/5] tags on claims.
    PRESERVE these confidence levels in your report. When a claim has borderline or low
    confidence (≤3), explicitly note the uncertainty: "Evidence suggests..." or
    "Preliminary data indicates..." rather than stating it as settled fact.

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

    # Pass 2a: Extract claims from report body BEFORE citation replacement
    # (claims need [src-N] / <cite> tags which are still present at this stage)
    if not evidence_claims:
        evidence_claims = _extract_claims_from_report(report_with_tags, sources)

    # Pass 2b: Replace citation tags with markdown links
    report_with_markdown = replace_citation_tags(report_with_tags, sources)

    appendix = build_evidence_appendix(sources, evidence_claims, evidence_gaps)
    if appendix.strip():
        report_with_markdown = f"{report_with_markdown.rstrip()}\n\n{appendix}\n"

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
