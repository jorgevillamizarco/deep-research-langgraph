"""Researcher node — two-phase web research execution.

Replicates ADK's ``section_researcher`` agent.

Phase 1 (RESEARCH): For each [RESEARCH] goal in the plan, generate 4-5 search
queries, execute all via web search, synthesize summaries.

Phase 2 (DELIVERABLE): For each [DELIVERABLE] goal, produce the requested artifact
using only Phase 1 summaries. No new searches.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import config
from app.state import ResearchState
from app.tools.citations import extract_citations_from_content
from app.tools.search import format_search_results, get_search_tool

logger = logging.getLogger(__name__)

# Regex to extract [RESEARCH] and [DELIVERABLE] goals from a plan
_GOAL_RE = re.compile(r"\[(RESEARCH|DELIVERABLE)\](?:\[(MODIFIED|NEW|IMPLIED)\])?\s*[:-]?\s*(.+?)(?=\n\[(?:RESEARCH|DELIVERABLE)\]|\Z)", re.DOTALL)


def _parse_goals(plan: str) -> dict[str, list[str]]:
    """Split a research plan into RESEARCH and DELIVERABLE goal lists."""
    research_goals = []
    deliverable_goals = []

    for match in _GOAL_RE.finditer(plan):
        goal_type = match.group(1)
        goal_text = match.group(3).strip()
        if goal_type == "RESEARCH":
            research_goals.append(goal_text)
        else:
            deliverable_goals.append(goal_text)

    return {"research": research_goals, "deliverable": deliverable_goals}


def _research_single_goal(goal: str, search_tool: Any, llm: Any) -> str:
    """Research a single [RESEARCH] goal: generate queries, search, synthesize.

    Returns a markdown summary string.
    """
    # Step 1: Generate 4-5 search queries for this goal
    query_prompt = f"""You are a research specialist. For the following research goal, generate 4-5 highly specific web search queries.

Goal: {goal}

Return ONLY a JSON array of strings, one query per item. Example:
["query one", "query two", "query three"]"""

    query_response = llm.invoke([
        SystemMessage(content="You generate search queries. Return only a JSON array of strings."),
        HumanMessage(content=query_prompt),
    ])

    # Parse the queries (handle both JSON and list-like text responses)
    queries = _parse_queries(query_response.content)

    if not queries:
        logger.warning("No search queries generated for goal: %s", goal[:80])

    # Step 2: Execute all searches
    search_results = []
    for query in queries:
        try:
            results = search_tool.invoke({"query": query, "max_results": 5})
            search_results.append(format_search_results(query, results))
        except Exception as e:
            logger.warning("Search failed for query %r: %s", query, e)
            search_results.append(f"### Search Results: {query}\nSearch failed: {e}\n")

    # Step 3: Synthesize findings
    combined_searches = "\n\n".join(search_results)

    synthesis_prompt = f"""You are a research analyst. Synthesize the search results below into a detailed, coherent summary.

RESEARCH GOAL: {goal}

SEARCH RESULTS:
{combined_searches}

Write a comprehensive summary that directly addresses the goal. Include specific findings, data points, and cite sources using markdown links [Title](URL). If sources conflict, note the discrepancy.

PER-CLAIM CONFIDENCE: After every factual claim, append a confidence tag:
  [CONFIDENCE:5] — direct measurement, primary source, or official data
  [CONFIDENCE:4] — well-supported by multiple authoritative sources
  [CONFIDENCE:3] — reasonable inference from available evidence
  [CONFIDENCE:2] — plausible but weakly sourced or speculative
  [CONFIDENCE:1] — educated guess, no direct evidence

TAG EVERY CLAIM. Do not skip the confidence tag on any factual statement."""

    synthesis = llm.invoke([
        SystemMessage(content="You are a research analyst synthesizing search results into clear summaries."),
        HumanMessage(content=synthesis_prompt),
    ])

    return f"### Research: {goal}\n\n{synthesis.content.strip()}\n"


def _parse_queries(content: str) -> list[str]:
    """Parse search queries from LLM response — handles JSON and plain text lists."""
    # Try JSON first
    try:
        import json as json_mod
        parsed = json_mod.loads(content)
        if isinstance(parsed, list):
            return [str(q).strip(' "') for q in parsed if q]
    except (json.JSONDecodeError, ValueError):
        pass

    # Try extracting from numbered list
    queries = []
    for line in content.split("\n"):
        line = line.strip()
        # Match patterns like: 1. "query" or - "query" or just "query"
        line = re.sub(r'^[\d\.\-\*\]\s]*["\']?', '', line)
        line = line.strip('"\' ,.')
        if line and len(line) > 10:
            queries.append(line)

    return queries[:6]  # max 6 queries


def _produce_deliverable(goal: str, research_summaries: str, llm: Any) -> str:
    """Produce a single [DELIVERABLE] artifact from the accumulated research."""
    prompt = f"""You are a report writer. Using the research summaries below,
produce the requested deliverable.

DELIVERABLE GOAL: {goal}

RESEARCH SUMMARIES:
{research_summaries}

Produce the deliverable as specified. Be thorough and cite sources with markdown links.
Use ONLY the information in the research summaries above — do NOT perform new searches."""

    response = llm.invoke([
        SystemMessage(content="You produce research deliverables from existing findings."),
        HumanMessage(content=prompt),
    ])
    return f"### Deliverable: {goal}\n\n{response.content.strip()}\n"


def _get_llm() -> Any:
    """Get the chat model for research."""
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=config.worker_model,
        temperature=0.2,
        api_key=config.worker_api_key or None,
        base_url=config.worker_api_base or None,
    )


def researcher_node(state: ResearchState) -> dict:
    """Execute the research plan with two-phase execution (ADK-aligned).

    Phase 1: Execute all [RESEARCH] goals with web search.
    Phase 2: Execute all [DELIVERABLE] goals using only Phase 1 findings.
    """
    plan = state.get("research_plan", "")
    if not plan:
        return {"errors": ["No research plan to execute"]}

    goals = _parse_goals(plan)
    search_tool = get_search_tool()
    llm = _get_llm()

    # Phase 1: Research all goals
    logger.info("Starting Phase 1: Researching %d goals", len(goals["research"]))
    research_summaries = []
    for i, goal in enumerate(goals["research"]):
        logger.info("Researching goal %d/%d: %s...", i + 1, len(goals["research"]), goal[:60])
        summary = _research_single_goal(goal, search_tool, llm)
        research_summaries.append(summary)

    combined_research = "\n\n---\n\n".join(research_summaries)

    # Phase 2: Produce deliverables
    logger.info("Starting Phase 2: Producing %d deliverables", len(goals["deliverable"]))
    deliverables = []
    for i, goal in enumerate(goals["deliverable"]):
        logger.info("Producing deliverable %d/%d: %s...", i + 1, len(goals["deliverable"]), goal[:60])
        artifact = _produce_deliverable(goal, combined_research, llm)
        deliverables.append(artifact)

    combined_deliverables = "\n\n---\n\n".join(deliverables)

    # Combine everything
    full_findings = f"# Research Findings\n\n## Research Summaries\n\n{combined_research}"
    if deliverables:
        full_findings += f"\n\n## Deliverables\n\n{combined_deliverables}"

    # Extract citations from the findings
    existing_count = len(state.get("url_to_short_id", {}))
    new_sources, new_url_map = extract_citations_from_content(full_findings, existing_count)

    # Merge with existing sources
    merged_sources = {**state.get("sources", {}), **new_sources}
    merged_url_map = {**state.get("url_to_short_id", {}), **new_url_map}

    return {
        "section_research_findings": full_findings,
        "sources": merged_sources,
        "url_to_short_id": merged_url_map,
        "research_iteration": state.get("research_iteration", 0) + 1,
    }


def deliverable_node(state: ResearchState) -> dict:
    """Phase 2: Produce DELIVERABLE artifacts from accumulated Phase 1 research.

    Uses ALL merged research findings (from parallel researchers + any enhancer
    supplements) to produce [DELIVERABLE] goals. No new searches — synthesis only.

    This node lives INSIDE the refinement subgraph so that when the enhancer adds
    follow-up findings, deliverables are regenerated with the full augmented context.
    """
    plan = state.get("research_plan", "")
    findings = state.get("section_research_findings", "")

    if not plan or not findings:
        return {}

    goals = _parse_goals(plan)
    deliverable_goals = goals.get("deliverable", [])

    if not deliverable_goals:
        logger.info("No DELIVERABLE goals in plan — skipping Phase 2")
        return {}

    llm = _get_llm()
    logger.info("Phase 2: Producing %d deliverables from %d chars of research",
                len(deliverable_goals), len(findings))

    deliverables = []
    for i, goal in enumerate(deliverable_goals):
        logger.info("Deliverable %d/%d: %s...", i + 1, len(deliverable_goals), goal[:60])

        # Build a prompt that includes per-claim confidence and source tier awareness
        prompt = f"""You are a report writer producing a high-quality deliverable.
Using ONLY the research summaries below, produce the requested deliverable.

DELIVERABLE GOAL: {goal}

RESEARCH SUMMARIES (all Phase 1 findings):
{findings}

Produce the deliverable as specified. Be thorough and cite sources with markdown
links [Title](URL). Use ONLY the information above — do NOT perform new searches.

PER-CLAIM CONFIDENCE: After every factual claim, append a confidence tag:
  [CONFIDENCE:5] — direct measurement, primary source, or official data
  [CONFIDENCE:4] — well-supported by multiple authoritative sources
  [CONFIDENCE:3] — reasonable inference from available evidence
  [CONFIDENCE:2] — plausible but weakly sourced or speculative
  [CONFIDENCE:1] — educated guess, no direct evidence

TAG EVERY CLAIM. If sources conflict, note the discrepancy explicitly."""

        response = llm.invoke([
            SystemMessage(content="You produce research deliverables from existing findings. Never fabricate."),
            HumanMessage(content=prompt),
        ])
        deliverables.append(f"### Deliverable: {goal}\n\n{response.content.strip()}\n")

    combined_deliverables = "\n\n---\n\n".join(deliverables)

    # Replace the findings with combined research + deliverables for composer
    # Strip any previous deliverable section to avoid duplication on re-runs
    import re as _re
    cleaned_findings = _re.sub(
        r"\n*## Deliverables.*$", "", findings, flags=_re.DOTALL
    ).strip()

    merged = f"{cleaned_findings}\n\n## Deliverables\n\n{combined_deliverables}"

    # Extract new citations from deliverables
    existing_count = len(state.get("url_to_short_id", {}))
    new_sources, new_url_map = extract_citations_from_content(combined_deliverables, existing_count)

    return {
        "section_research_findings": merged,
        "sources": {**state.get("sources", {}), **new_sources},
        "url_to_short_id": {**state.get("url_to_short_id", {}), **new_url_map},
    }
