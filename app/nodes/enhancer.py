"""Enhanced search executor node — executes follow-up queries from the evaluator.

Replicates ADK's ``enhanced_search_executor``. Runs when the evaluator grades
"fail" and provides follow_up_queries. Executes all queries, merges findings
with existing research, and collects new sources.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import config
from app.state import ResearchState
from app.tools.citations import extract_citations_from_content
from app.tools.search import format_search_results, get_search_tool

logger = logging.getLogger(__name__)


def _get_llm() -> Any:
    """Get the chat model for enhancement."""
    from app.tokens import get_llm
    return get_llm(model=config.worker_model, api_key=config.worker_api_key or None,
                   base_url=config.worker_api_base or None, temperature=0.2,
                   node_name="enhancer")


def enhanced_search_executor_node(state: ResearchState) -> dict:
    """Execute follow-up queries from the evaluator and merge with existing findings.

    Returns updated state with:
    - section_research_findings: merged old + new findings
    - iteration_count: incremented
    - sources: updated with new sources from follow-up results
    """
    evaluation = state.get("research_evaluation")
    if not evaluation or evaluation.grade != "fail":
        logger.info("No enhancement needed — evaluation is pass or absent")
        return {
            "iteration_count": state.get("iteration_count", 0) + 1,
        }

    follow_ups = evaluation.follow_up_queries or []
    if not follow_ups:
        logger.info("No follow-up queries — skipping enhancement")
        return {
            "iteration_count": state.get("iteration_count", 0) + 1,
        }

    search_tool = get_search_tool()
    llm = _get_llm()
    topic = state.get("topic", "")
    existing_findings = state.get("section_research_findings", "")

    logger.info("Executing %d follow-up queries", len(follow_ups))

    # Execute all follow-up queries
    all_new_content = []
    new_sources_merged = {}
    new_url_map_merged = {}
    existing_count = len(state.get("url_to_short_id", {}))

    for query in follow_ups:
        query_text = query.search_query if hasattr(query, "search_query") else str(query)
        try:
            results = search_tool.invoke({"query": query_text, "max_results": 5})
            formatted = format_search_results(query_text, results)
            all_new_content.append(formatted)

            # Extract citations from these results
            counter = existing_count + len(new_url_map_merged)
            sources, url_map = extract_citations_from_content(formatted, counter)
            new_sources_merged.update(sources)
            new_url_map_merged.update(url_map)

        except Exception as e:
            logger.warning("Follow-up search failed for query %r: %s", query_text, e)
            all_new_content.append(f"### Search Results: {query_text}\nSearch failed: {e}\n")

    # Synthesize the new findings
    new_content_text = "\n\n".join(all_new_content)

    if new_content_text.strip():
        synthesis_prompt = f"""You are a research specialist filling specific gaps.
The initial research for "{topic}" was found incomplete. Below are additional search results.

EXISTING FINDINGS:
{existing_findings}

ADDITIONAL SEARCH RESULTS:
{new_content_text}

Synthesize THESE NEW RESULTS into supplementary findings. Focus specifically on filling
the gaps identified in the evaluation comment:
{evaluation.comment}

Write a coherent supplement that ADDS TO (not repeats) the existing findings.
Cite sources with markdown links."""

        synthesis = llm.invoke([
            SystemMessage(content="You fill research gaps with supplementary findings."),
            HumanMessage(content=synthesis_prompt),
        ])
        supplement = synthesis.content.strip()
    else:
        supplement = "No new search results were available for follow-up queries."

    # Merge: append supplement to existing findings
    merged = f"{existing_findings}\n\n---\n\n## Supplementary Findings (Refinement Round {state.get('iteration_count', 0) + 1})\n\n{supplement}"

    # Merge sources
    merged_sources = {**state.get("sources", {}), **new_sources_merged}
    merged_url_map = {**state.get("url_to_short_id", {}), **new_url_map_merged}

    logger.info("Enhancement complete — iteration %d", state.get("iteration_count", 0) + 1)
    print(f"  🔧 Enhanced — iteration {state.get('iteration_count', 0) + 1} ({len(follow_ups)} queries)", flush=True)

    return {
        "section_research_findings": merged,
        "sources": merged_sources,
        "url_to_short_id": merged_url_map,
        "iteration_count": state.get("iteration_count", 0) + 1,
        **llm.token_delta(),
    }
