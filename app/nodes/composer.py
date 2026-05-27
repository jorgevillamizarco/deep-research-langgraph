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
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=config.critic_model,
        temperature=0.2,
        api_key=config.critic_api_key or config.worker_api_key or None,
        base_url=config.critic_api_base or config.worker_api_base or None,
    )


def _serialize_sources(sources: dict) -> str:
    """Serialize sources dict to a compact JSON string for the LLM prompt."""
    serializable = {}
    for sid, src in sources.items():
        # Convert any non-serializable objects to strings
        serializable[sid] = {
            k: str(v) if not isinstance(v, (str, int, float, bool, list, dict, type(None))) else v
            for k, v in src.items()
        }
    return json.dumps(serializable, indent=2)


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

    if not findings:
        return {
            "final_cited_report": "No research findings were generated.",
            "final_report_with_citations": "No research findings were generated.",
        }

    llm = _get_llm()
    sources_json = _serialize_sources(sources)

    eval_note = ""
    if evaluations:
        eval_note = f"\nThe research was evaluated as: {evaluations.grade.upper()}\nEvaluator comment: {evaluations.comment}\n"

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
    - Topic: {topic}

    REPORT STRUCTURE (follow this exactly):
    # {topic}: Deep Research Report
    ## Executive Summary
    [3-5 paragraphs. Standalone — readable without reading the full report.]

    ## [Section per topic from the report outline]
    [Detailed findings with inline citations. Use <cite source="src-N"/> after each claim.]

    ## Cross-Cutting Themes
    [Patterns across sections. Note any contradictions.]

    ## Gaps & Uncertainties
    [What's missing or unclear.]

    ## Methodology
    [Brief note on how the research was conducted: web search, iterative refinement, etc.]

    COMPOSITION RULES:
    1. Every factual claim must have an inline citation tag.
    2. All content must be inline — never reference external files.
    3. Flag contradictions between different findings explicitly.
    4. Preserve specific numbers, dates, and technical details.
    5. Do NOT include a "References" or "Sources" section — all citations are inline.
    6. The Executive Summary must be completely standalone."""

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Produce the final research report for: {topic}"),
        ])
        report_with_tags = response.content.strip()

    except Exception as e:
        logger.error("Composer LLM call failed: %s", e)
        return {
            "final_cited_report": f"Report generation failed: {e}",
            "final_report_with_citations": f"Report generation failed: {e}",
            "errors": state.get("errors", []) + [f"Composer error: {e}"],
        }

    # Pass 2: Replace citation tags with markdown links
    report_with_markdown = replace_citation_tags(report_with_tags, sources)

    return {
        "final_cited_report": report_with_tags,
        "final_report_with_citations": report_with_markdown,
    }
