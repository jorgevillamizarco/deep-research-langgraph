"""Enhanced search executor node — executes follow-up queries from the evaluator.

Replicates ADK's ``enhanced_search_executor``. Runs when the evaluator grades
"fail" and provides follow_up_queries. Executes all queries, merges findings
with existing research, and collects new sources.
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


def _get_llm() -> Any:
    """Get the chat model for enhancement."""
    from app.tokens import get_llm
    return get_llm(model=config.worker_model, api_key=config.worker_api_key or None,
                   base_url=config.worker_api_base or None, temperature=0.2,
                   node_name="enhancer")


def _word_set(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", text.lower()) if len(word) > 2}


def _gap_matches_query(gap_description: str, query_text: str) -> bool:
    gap_words = _word_set(gap_description)
    query_words = _word_set(query_text)
    if not gap_words or not query_words:
        return False
    return len(gap_words & query_words) >= 2


def _has_missing_language(text: str) -> bool:
    return bool(re.search(r"(?im)(not found|missing|could not retrieve|unconfirmed)", text))


def _has_positive_evidence(text: str) -> bool:
    return bool(re.search(r"\[[^\]]+\]\(https?://[^\)]+\)", text) or re.search(r"https?://\S+", text))


_GAP_REGEX = re.compile(
    r"(?im)^(?!#)(?:(?!search results|original evaluation|previously missing|filling missing))"
    r".*(not found|missing|could not retrieve|unconfirmed).*$"
)


def _is_meta_commentary(text: str) -> bool:
    return bool(re.search(r"(search results|original evaluation|previously missing|filling missing|deficiencies identified|addressed in|synthesis incorporates|impact on previous findings)", text, re.IGNORECASE))


def _refresh_evidence_gaps(existing_gaps: list[dict], follow_ups: list, supplement: str) -> list[dict]:
    targeted_queries = []
    for query in follow_ups:
        if isinstance(query, str):
            targeted_queries.append(query)
        else:
            targeted_queries.append(query.search_query if hasattr(query, "search_query") else str(query))

    refreshed_gaps = []
    for gap in existing_gaps:
        description = str((gap or {}).get("description", "")).strip()
        if not description:
            continue
        addressed = any(_gap_matches_query(description, query_text) for query_text in targeted_queries)
        if addressed and supplement.strip() and _has_positive_evidence(supplement) and not _has_missing_language(supplement):
            continue
        refreshed_gaps.append(gap)

    for match in _GAP_REGEX.finditer(supplement):
        description = match.group(0).strip()
        if _is_meta_commentary(description):
            continue
        if any(str((gap or {}).get("description", "")).strip() == description for gap in refreshed_gaps):
            continue
        refreshed_gaps.append({
            "gap_id": f"gap-{len(refreshed_gaps) + 1}",
            "description": description,
            "why_it_matters": "This missing evidence weakens confidence in the conclusion.",
            "impact_on_conclusion": "unknown",
        })

    return refreshed_gaps


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

    follow_ups = []
    sufficiency = state.get("sufficiency_assessment") or {}
    targeted_queries = [str(query).strip() for query in sufficiency.get("follow_up_queries", []) if str(query).strip()]
    if targeted_queries:
        follow_ups = targeted_queries
    else:
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
    existing_url_map = dict(state.get("url_to_short_id", {}))
    existing_count = len(existing_url_map)

    for query in follow_ups:
        if isinstance(query, str):
            query_text = query
        else:
            query_text = query.search_query if hasattr(query, "search_query") else str(query)
        try:
            results = search_tool.invoke({"query": query_text, "max_results": 5})
            formatted = format_search_results(query_text, results)
            all_new_content.append(formatted)

            # Extract citations, remapping duplicates to existing IDs
            counter = existing_count + len(new_url_map_merged)
            sources, url_map = extract_citations_from_content(formatted, counter)

            # Remap: if URL already exists, reuse existing short_id
            remapped_sources = {}
            remapped_url_map = {}
            for sid, src in sources.items():
                url = src.get("url", "")
                canonical_sid = existing_url_map.get(url)
                if canonical_sid and canonical_sid != sid:
                    remapped_sources[canonical_sid] = src
                    remapped_url_map[url] = canonical_sid
                else:
                    remapped_sources[sid] = src
                    remapped_url_map[url] = sid

            new_sources_merged.update(remapped_sources)
            new_url_map_merged.update(remapped_url_map)

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

        try:
            synthesis = llm.invoke([
                SystemMessage(content="You fill research gaps with supplementary findings."),
                HumanMessage(content=synthesis_prompt),
            ])
            supplement = synthesis.content.strip()
        except Exception as e:
            logger.warning("Enhancement synthesis failed: %s", e)
            print(f"  WARNING  Enhancement failed ({e}) returning Phase 1 findings", flush=True)
            return {
                "section_research_findings": existing_findings,
                "sources": state.get("sources", {}),
                "url_to_short_id": state.get("url_to_short_id", {}),
                "evidence_gaps": state.get("evidence_gaps", []),
                "iteration_count": state.get("iteration_count", 0) + 1,
                "errors": state.get("errors", []) + [f"Enhancement failed: {e}"],
            }
    else:
        supplement = "No new search results were available for follow-up queries."

    # Merge: append supplement to existing findings
    merged = f"{existing_findings}\n\n---\n\n## Supplementary Findings (Refinement Round {state.get('iteration_count', 0) + 1})\n\n{supplement}"
    refreshed_gaps = _refresh_evidence_gaps(state.get("evidence_gaps", []) or [], follow_ups, supplement)

    # Merge sources
    merged_sources = {**state.get("sources", {}), **new_sources_merged}
    merged_url_map = {**state.get("url_to_short_id", {}), **new_url_map_merged}

    logger.info("Enhancement complete — iteration %d", state.get("iteration_count", 0) + 1)
    print(f"  🔧 Enhanced — iteration {state.get('iteration_count', 0) + 1} ({len(follow_ups)} queries)", flush=True)

    return {
        "section_research_findings": merged,
        "sources": merged_sources,
        "url_to_short_id": merged_url_map,
        "evidence_gaps": refreshed_gaps,
        "iteration_count": state.get("iteration_count", 0) + 1,
        **llm.token_delta(),
    }
