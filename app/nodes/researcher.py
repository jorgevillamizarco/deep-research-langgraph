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
from app.models import Citation, ResearchFinding
from app.state import ResearchState
from app.tools.citations import extract_citations_from_content
from app.tools.search import format_search_results, get_search_tool, fetch_url_content

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


def _research_single_goal(goal: str, search_tool: Any, llm: Any) -> ResearchFinding:
    """Research a single [RESEARCH] goal: generate queries, search, synthesize.

    Returns a structured ResearchFinding with pre-extracted citations.
    """
    # Step 1: Generate 4-5 search queries for this goal
    # Extract language hints from goal annotations (e.g., "search in Spanish")
    lang_match = re.search(r'(?:search|buscar|rechercher)\s+(?:in|using|language:?\s+|en|auf)\s+([^;)]+)', goal, re.IGNORECASE)
    target_lang = lang_match.group(1).strip().rstrip('.') if lang_match else None

    query_prompt = f"""You are a research specialist. For the following research goal, generate 4-5 highly specific web search queries.
{f'''IMPORTANT: Generate ALL queries in {target_lang}. Search for {target_lang}-language sources on {target_lang}-language websites.''' if target_lang else ''}

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
    all_urls: list[str] = []
    for query in queries:
        try:
            results = search_tool.invoke({"query": query, "max_results": 5})
            search_results.append(format_search_results(query, results))
            for r in results[:2]:  # collect top 2 URLs per query for deep fetch
                url = r.get("url", "")
                if url and url not in all_urls:
                    all_urls.append(url)
        except Exception as e:
            logger.warning("Search failed for query %r: %s", query, e)
            search_results.append(f"### Search Results: {query}\nSearch failed: {e}\n")

    # Step 2b: Fetch full content from top URLs with browser for the #1 result
    # HTTP for all 3 (fast), browser with link-following for the first (deep)
    fetched_content = []
    for i, url in enumerate(all_urls[:3]):
        content = fetch_url_content(url, max_chars=5000)
        if content:
            fetched_content.append(f"## Source: {url}\n\n{content}\n")
        # For the top result, also try browser with link-following for richer context
        if i == 0 and content and len(content) < 3000:
            # HTTP gave sparse content — browser might find more
            from app.tools.search import _fetch_via_browser
            browser_content = _fetch_via_browser(url, max_chars=5000, follow_links=1)
            if browser_content and len(browser_content) > len(content):
                fetched_content[-1] = f"## Source (browser): {url}\n\n{browser_content[:5000]}\n"
    if fetched_content:
        search_results.append("\n\n### Full-Page Content\n" + "\n".join(fetched_content))

    # Step 3: Synthesize findings
    combined_searches = "\n\n".join(search_results)

    synthesis_prompt = f"""You are a research analyst. Synthesize the search results below into a detailed, coherent summary.
{f'''NOTE: Sources may be in {target_lang}. Translated claims are acceptable — preserve original terminology in parentheses where relevant.''' if target_lang else ''}

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

    summary = synthesis.content.strip()

    # Step 3b: Verification pass — cross-check findings with targeted search
    verification_note = _verify_findings(goal, summary, search_tool)
    if verification_note:
        summary += "\n\n" + verification_note

    # Step 4: Extract citations from the synthesized summary
    # (Pre-extract so they don't get lost in parallel merging)
    _dummy_sources, _dummy_map = extract_citations_from_content(summary, 0)
    citations = [
        Citation(
            short_id=sid,
            url=src.get("url", ""),
            title=src.get("title", ""),
            tier=src.get("tier", 3),
        )
        for sid, src in _dummy_sources.items()
    ]

    return ResearchFinding(
        goal_text=goal,
        summary=summary,
        citations=citations,
        search_queries=queries,
    )


def _verify_findings(goal: str, summary: str, search_tool: Any) -> str:
    """Run a targeted verification search to catch domain mismatches.

    Generates a disambiguating query that includes the goal plus contextual
    keywords from the synthesis. If the verification surfaces significantly
    different information, returns a verification note to append.

    This catches errors like finding "PRR (manufacturing review)" when the
    user meant "PRR (software production readiness)."
    """
    import re

    # Extract key terms from synthesis for cross-reference
    summary_lower = summary.lower()
    # Domain-specific disambiguation terms to try
    disambiguators = []
    if any(t in summary_lower for t in ["manufacturing", "supply chain", "hardware", "production line"]):
        disambiguators.append("software engineering")
    if any(t in summary_lower for t in ["military", "defense", "acquisition", "weapon"]):
        disambiguators.append("software development")

    if not disambiguators:
        # No concerning terms found — skip verification (avoid noise)
        return ""

    # Build verification query: original goal + disambiguation
    verify_query = f"{goal} {' '.join(disambiguators)}"
    logger.info("Verification pass: searching %r", verify_query[:80])

    try:
        results = search_tool.invoke({"query": verify_query, "max_results": 3})
        if not results:
            return ""

        # Quick synthesis of verification results
        result_text = "\n".join(
            f"- {r.get('title', '')}: {r.get('content', r.get('snippet', ''))[:300]}"
            for r in results[:3]
        )

        # Check if verification results are substantially different
        result_lower = result_text.lower()
        if any(t in result_lower for t in ["software", "devops", "deployment", "monitoring", "observability"]):
            note = (
                "## Verification Note\n\n"
                "A cross-check search suggests the findings above may describe a different domain "
                "than intended. A targeted verification search found:\n\n"
                f"{result_text}\n\n"
                "Consider whether these alternative interpretations apply to the original question."
            )
            logger.info("Verification found alternative domain context")
            return note

    except Exception as e:
        logger.debug("Verification search failed: %s", e)

    return ""


def _parse_queries(content: str) -> list[str]:
    """Parse search queries from LLM response — handles JSON and plain text lists."""
    import json as json_mod
    # Try JSON first
    try:
        parsed = json_mod.loads(content)
        if isinstance(parsed, list):
            return [str(q).strip(' "') for q in parsed if q]
    except (json_mod.JSONDecodeError, ValueError):
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
    from app.tokens import get_llm
    return get_llm(model=config.worker_model, api_key=config.worker_api_key or None,
                   base_url=config.worker_api_base or None, temperature=0.2,
                   node_name="researcher")


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
        finding = _research_single_goal(goal, search_tool, llm)
        research_summaries.append(finding.to_markdown())

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
        **llm.token_delta(),
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

    # Failsafe: if plan has [DELIVERABLE] tag but regex didn't catch it
    if not deliverable_goals and "[DELIVERABLE]" in plan:
        deliverable_goals = ["Synthesize all research findings into a comprehensive deliverable"]
        logger.info("Failsafe: extracted DELIVERABLE from plan tag")

    if not deliverable_goals:
        logger.info("No DELIVERABLE goals in plan — skipping Phase 2")
        return {}

    llm = _get_llm()
    logger.info("Phase 2: Producing %d deliverables from %d chars of research",
                len(deliverable_goals), len(findings))
    print(f"  📝 Phase 2: {len(deliverable_goals)} deliverables from {len(findings):,} chars", flush=True)

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
        **llm.token_delta(),
    }
