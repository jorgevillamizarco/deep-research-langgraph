"""LangGraph deep research agent — main graph definition.

Builds the top-level StateGraph and the iterative refinement subgraph.

Graph architecture (ADK-aligned):

    planner (plan_generator + section_planner + interrupt)
      │
      ▼
    researcher (section_researcher: two-phase execution)
      │
      ▼
    [refinement_subgraph]  ◄──────────────────────┐
      │  evaluator (research_evaluator)            │
      │    ├─ pass ──► exit subgraph               │
      │    └─ fail ──► enhancer ───────────────────┘ (loop, iteration++)
      │
      ▼
    composer (report_composer + citation replacement)
"""

from __future__ import annotations

import logging
from typing import Any, Literal, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import END
from langgraph.graph import StateGraph

from app.nodes import (
    composer_node,
    enhanced_search_executor_node,
    planner_node,
    research_evaluator_node,
    researcher_node,
)
from app.state import ResearchState

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Conditional routing functions
# ──────────────────────────────────────────────


def route_after_evaluation(state: ResearchState) -> Literal["enhancer", "pass"]:
    """Route after evaluator: loop to enhancer if FAIL, exit if PASS.

    Also exits if max iterations reached.
    """
    evaluation = state.get("research_evaluation")
    iteration_count = state.get("iteration_count", 0)
    max_iterations = state.get("max_iterations", 5)

    if evaluation and evaluation.grade == "pass":
        logger.info("Evaluation: PASS — exiting refinement loop")
        return "pass"

    if iteration_count >= max_iterations:
        logger.warning(
            "Max iterations (%d) reached — exiting refinement loop",
            max_iterations,
        )
        return "pass"

    logger.info(
        "Evaluation: FAIL — iterating (%d/%d)",
        iteration_count,
        max_iterations,
    )
    return "enhancer"


# ──────────────────────────────────────────────
# Build refinement subgraph
# ──────────────────────────────────────────────


def build_refinement_subgraph() -> StateGraph:
    """Build the iterative refinement loop subgraph.

    Mirrors ADK's LoopAgent([research_evaluator, EscalationChecker,
    enhanced_search_executor]).
    """
    builder = StateGraph(ResearchState)

    builder.add_node("evaluator", research_evaluator_node)
    builder.add_node("enhancer", enhanced_search_executor_node)

    # Conditional edge: evaluator → enhancer (fail) or exit (pass)
    builder.add_conditional_edges(
        "evaluator",
        route_after_evaluation,
        {
            "enhancer": "enhancer",
            "pass": END,
        },
    )

    # After enhancer, loop back to evaluator
    builder.add_edge("enhancer", "evaluator")

    builder.set_entry_point("evaluator")

    return builder


# ──────────────────────────────────────────────
# Build main research graph
# ──────────────────────────────────────────────


def build_research_graph(
    checkpointer: Optional[Any] = None,
) -> StateGraph:
    """Build and compile the deep research graph.

    Args:
        checkpointer: Optional LangGraph checkpointer (default: MemorySaver).

    Returns:
        A compiled ``StateGraph`` ready for invocation.
    """
    checkpointer = checkpointer or MemorySaver()

    builder = StateGraph(ResearchState)

    # Build and attach the refinement subgraph
    refinement_subgraph = build_refinement_subgraph().compile()

    # Add nodes
    builder.add_node("planner", planner_node)
    builder.add_node("researcher", researcher_node)
    builder.add_node("refinement_loop", refinement_subgraph)
    builder.add_node("composer", composer_node)

    # Define edges
    builder.set_entry_point("planner")

    # After planner, always go to researcher
    builder.add_edge("planner", "researcher")

    # After researcher, enter the refinement subgraph
    builder.add_edge("researcher", "refinement_loop")

    # After refinement loop exits, go to composer
    builder.add_edge("refinement_loop", "composer")

    # After composer, we're done
    builder.add_edge("composer", END)

    return builder.compile(checkpointer=checkpointer)
