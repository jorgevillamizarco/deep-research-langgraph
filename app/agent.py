"""LangGraph deep research agent — main graph definition.

Graph architecture (ADK-aligned with parallel fan-out + two-phase execution):

    planner (plan_generator + section_planner + interrupt)
      │
      ├─► Send ─► parallel_researcher(goal 1) ─┐
      ├─► Send ─► parallel_researcher(goal 2) ─┤── fan-in (merge)
      ...  (N parallel researchers)            │
      ├─► Send ─► parallel_researcher(goal N) ─┘
      │
      ▼
    [refinement_subgraph]
      │  deliverable → evaluator → enhancer → deliverable (loop)
      │  Phase 2: DELIVERABLE goals synthesized from ALL Phase 1 findings.
      │  Enhancer supplements feed back into full deliverable regeneration.
      │
      ▼
    composer (report_composer + citation replacement)
"""

from __future__ import annotations

import logging
from typing import Optional

from langgraph.checkpoint.memory import MemorySaver
try:
    from langgraph.checkpoint.sqlite import SqliteSaver
except ImportError:
    try:
        from langgraph_checkpoint_sqlite import SqliteSaver
    except ImportError:
        SqliteSaver = None  # type: ignore[assignment]
from langgraph.constants import END
from langgraph.types import Send
from langgraph.graph import StateGraph

from app.nodes import (
    composer_node,
    deliverable_node,
    enhanced_search_executor_node,
    planner_node,
    report_critic_node,
    research_evaluator_node,
    researcher_node,
)
from app.state import ResearchState

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Conditional routing functions
# ──────────────────────────────────────────────


def route_after_evaluation(state: ResearchState):
    """Route after evaluator: loop to enhancer if FAIL, exit if PASS.

    Includes circuit breaker: if scores stagnate across 2 consecutive enhancer
    cycles (no improvement), force-exit to avoid wasted iterations.
    """
    evaluation = state.get("research_evaluation")
    sufficiency = state.get("sufficiency_assessment") or {}
    has_blocking_gaps = not sufficiency.get("information_sufficient", True)
    iteration_count = state.get("iteration_count", 0)
    max_iterations = state.get("max_iterations", 5)

    if has_blocking_gaps:
        if sufficiency.get("recommendation_strength") == "no_recommendation":
            return "pass"
        if iteration_count >= max_iterations:
            return "pass"
        return "enhancer"

    if evaluation and evaluation.grade == "pass":
        return "pass"
    if iteration_count >= max_iterations:
        return "pass"

    # Circuit breaker: detect score stagnation
    scores = state.get("evaluation_scores", [])
    if len(scores) >= 2:
        # Get total scores for last two iterations
        def _total(s):
            return s.get("source_quality", 0) + s.get("claim_verification", 0) + s.get("completeness", 0)
        last_two = sorted(scores, key=lambda s: s.get("iteration", 0))[-2:]
        if _total(last_two[0]) >= _total(last_two[1]):
            logger.info(
                "Circuit breaker: scores stagnant at %d/%d across iterations "
                "%d-%d — forcing pass",
                _total(last_two[1]), 15,
                last_two[0].get("iteration", 0), last_two[1].get("iteration", 0),
            )
            return "pass"

    return "enhancer"


def route_after_planner(state: ResearchState):
    """After planner: fan out to N parallel researchers, one per goal."""
    goals = state.get("parallel_goals", [])
    if not goals:
        # Fallback: go directly to researcher if no parallel goals
        return "researcher"

    # Fan out: one Send per goal
    return [
        Send("parallel_researcher", {"current_goal": g})
        for g in goals
    ]


# ──────────────────────────────────────────────
# Parallel researcher node
# ──────────────────────────────────────────────


def parallel_researcher_node(state: ResearchState) -> dict:
    """Research a single goal in parallel. Called once per goal via Send().

    This is lighter than the full researcher_node — it does one goal,
    not all goals. Results accumulate via state.parallel_findings reducer.
    """
    from app.nodes.researcher import _get_llm, _parse_queries, _research_single_goal

    goal = state.get("current_goal", "")
    if not goal:
        return {"parallel_findings": ["No goal assigned"]}

    from app.tools.search import get_search_tool, format_search_results

    search_tool = get_search_tool()
    llm = _get_llm()

    finding = _research_single_goal(goal, search_tool, llm)
    text = finding.to_markdown()

    logger.info(
        "Parallel researcher done: goal=%s... result=%d chars",
        goal[:60],
        len(text),
    )
    print(f"  ✓ [{goal[:60]}...] ({len(text):,} chars)", flush=True)
    # Return typed finding — citations travel with the object, no regex needed
    return {"parallel_findings": [finding]}


# ──────────────────────────────────────────────
# Merge node: combines parallel findings
# ──────────────────────────────────────────────


def merge_findings_node(state: ResearchState) -> dict:
    """Merge all parallel research findings into a single research output.

    Uses typed accessors to avoid regex citation extraction — citations are
    carried in ResearchFinding models from _research_single_goal().
    """
    import re

    from app.models import ResearchFinding
    from app.tools.citations import annotate_source_tier

    raw_findings = state.get("parallel_findings", [])
    findings_text = "\n\n---\n\n".join(
        f.to_markdown() if isinstance(f, ResearchFinding) else str(f)
        for f in raw_findings
    ) if raw_findings else ""

    logger.info("Merged %d parallel findings (%d chars)", len(raw_findings), len(findings_text))
    print(f"  📦 Phase 1 complete — {len(raw_findings)} goals, {len(findings_text):,} chars", flush=True)

    all_sources: dict = dict(state.get("sources", {}))
    all_url_map: dict = dict(state.get("url_to_short_id", {}))
    evidence_claims: list[dict] = []
    evidence_gaps: list[dict] = []
    existing_numeric_ids = [
        int(sid.removeprefix("src-"))
        for sid in all_sources
        if isinstance(sid, str) and sid.startswith("src-") and sid.removeprefix("src-").isdigit()
    ]
    next_source_id = (max(existing_numeric_ids) + 1) if existing_numeric_ids else 1

    def _canonical_source_id(url: str) -> str:
        nonlocal next_source_id
        existing = all_url_map.get(url)
        if existing:
            return existing
        short_id = f"src-{next_source_id}"
        next_source_id += 1
        all_url_map[url] = short_id
        return short_id

    for finding in raw_findings:
        if not isinstance(finding, ResearchFinding):
            continue

        for citation in finding.citations:
            sid = _canonical_source_id(citation.url)
            source = {
                "short_id": sid,
                "url": citation.url,
                "title": citation.title or citation.url,
                "domain": citation.url.split("/")[2] if "://" in citation.url else "",
                "tier": citation.tier,
                "authority_reason": citation.authority_reason,
                "supported_claims": citation.supported_claims,
                "used_for_claims": [],
            }
            if sid not in all_sources:
                all_sources[sid] = annotate_source_tier(source)

        for idx, tag in enumerate(finding.confidence_tags, start=1):
            claim_id = f"claim-{len(evidence_claims) + 1}"
            support_source_ids = [all_url_map[c.url] for c in finding.citations if c.url in all_url_map]
            evidence_claims.append({
                "claim_id": claim_id,
                "text": tag.claim_text or f"Claim {idx} from {finding.goal_text}",
                "section": finding.goal_text,
                "confidence": tag.score,
                "support_source_ids": support_source_ids,
                "evidence_strength": "high" if tag.score >= 4 else "medium" if tag.score == 3 else "low",
            })
            for sid in support_source_ids:
                all_sources[sid].setdefault("used_for_claims", []).append(claim_id)

        for match in re.finditer(
            r"(?im)^(?!#)(?:(?!search results|original evaluation|previously missing|filling missing))"
            r".*(not found|missing|could not retrieve|unconfirmed).*$",
            finding.summary,
        ):
            description = match.group(0).strip()
            if re.search(r"(search results|original evaluation|previously missing|filling missing)", description, re.IGNORECASE):
                continue
            evidence_gaps.append({
                "gap_id": f"gap-{len(evidence_gaps) + 1}",
                "description": description,
                "why_it_matters": "This missing evidence weakens confidence in the conclusion.",
                "impact_on_conclusion": "unknown",
            })

    # Fallback: regex extraction for string findings (backward compat)
    if not all_sources and findings_text:
        from app.tools.citations import extract_citations_from_content
        extracted_sources, extracted_url_map = extract_citations_from_content(findings_text)
        all_sources = extracted_sources
        all_url_map = extracted_url_map

    return {
        "section_research_findings": findings_text,
        "sources": all_sources,
        "url_to_short_id": all_url_map,
        "evidence_claims": evidence_claims,
        "evidence_gaps": evidence_gaps,
    }


# ──────────────────────────────────────────────
# Build refinement subgraph (Phase 2 + critique)
# ──────────────────────────────────────────────


def build_refinement_subgraph() -> StateGraph:
    """Build the refinement subgraph with two-phase execution baked in.

    deliverable → evaluator → enhancer → deliverable (loop until PASS or max)

    The deliverable node runs Phase 2: DELIVERABLE goals synthesized from
    ALL Phase 1 research findings. When enhancer adds follow-up findings,
    deliverable regenerates with the full augmented context — not a shallow
    append.
    """
    builder = StateGraph(ResearchState)

    builder.add_node("deliverable", deliverable_node)
    builder.add_node("evaluator", research_evaluator_node)
    builder.add_node("enhancer", enhanced_search_executor_node)

    builder.add_conditional_edges(
        "evaluator",
        route_after_evaluation,
        {"enhancer": "enhancer", "pass": END},
    )

    builder.add_edge("enhancer", "deliverable")
    builder.add_edge("deliverable", "evaluator")
    builder.set_entry_point("deliverable")

    return builder


# ──────────────────────────────────────────────
# Build main research graph
# ──────────────────────────────────────────────


def build_research_graph(checkpointer=None):
    """Build and compile the deep research graph with parallel research.

    Args:
        checkpointer: Optional LangGraph checkpointer (default: SqliteSaver).

    Returns:
        A compiled StateGraph ready for invocation.
    """
    if checkpointer is None:
        import os
        import sqlite3
        db_path = os.getenv("CHECKPOINT_DB_PATH", "checkpoints.db")
        try:
            conn = sqlite3.connect(db_path, check_same_thread=False)
            checkpointer = SqliteSaver(conn)
        except Exception:
            checkpointer = MemorySaver()

    builder = StateGraph(ResearchState)

    # Build refinement subgraph
    refinement_subgraph = build_refinement_subgraph().compile()

    # Add nodes
    builder.add_node("planner", planner_node)
    builder.add_node("researcher", researcher_node)  # fallback (no parallel goals)
    builder.add_node("parallel_researcher", parallel_researcher_node)
    builder.add_node("merge_findings", merge_findings_node)
    builder.add_node("refinement_loop", refinement_subgraph)
    builder.add_node("composer", composer_node)
    builder.add_node("report_critic", report_critic_node)

    # Conditional fan-out from planner: Send to parallel researchers
    builder.add_conditional_edges(
        "planner",
        route_after_planner,
        {"researcher": "researcher", "parallel_researcher": "parallel_researcher"},
    )

    # After parallel researchers complete → merge
    builder.add_edge("parallel_researcher", "merge_findings")
    builder.add_edge("researcher", "merge_findings")
    builder.add_edge("merge_findings", "refinement_loop")
    builder.add_edge("refinement_loop", "composer")
    builder.add_edge("composer", "report_critic")
    builder.add_edge("report_critic", END)

    builder.set_entry_point("planner")

    return builder.compile(checkpointer=checkpointer)
