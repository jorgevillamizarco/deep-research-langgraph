"""Planner node — plan generation, section outlining, and parallel goal extraction.

Replicates ADK's ``plan_generator`` and ``section_planner`` agents.
Two LLM calls in sequence:
1. Plan generator: 5 action-oriented research goals with [RESEARCH]/[DELIVERABLE] tags
2. Section planner: Markdown report outline with 4-6 sections

If ``user_feedback`` exists in state, refines the existing plan with
[MODIFIED]/[NEW]/[IMPLIED] tags.

Extracts ``parallel_goals`` from the plan for LangGraph Send() fan-out
so multiple researchers execute concurrently.

Uses ``interrupt()`` for human-in-the-loop plan approval.
"""

from __future__ import annotations

import datetime
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import config
from app.state import ResearchState

logger = logging.getLogger(__name__)


def _get_llm() -> Any:
    """Get the chat model for planning (uses worker_model from config)."""
    from app.tokens import get_llm
    return get_llm(model=config.worker_model, temperature=0.1,
                   api_key=config.worker_api_key or None,
                   base_url=config.worker_api_base or None)


def _generate_plan(topic: str, previous_plan: str | None, user_feedback: str | None,
                   llm: Any | None = None) -> str:
    """Call the LLM to generate or refine a research plan."""
    if llm is None:
        llm = _get_llm()
    today = datetime.datetime.now().strftime("%Y-%m-%d")

    if previous_plan and user_feedback:
        system_prompt = f"""You are a research strategist. Improve the existing research plan based on user feedback.
Mark changes with: [MODIFIED], [NEW], [IMPLIED], [REMOVED].
Maintain the original sequential order. Current date: {today}"""
        user_prompt = f"TOPIC: {topic}\n\nEXISTING PLAN:\n{previous_plan}\n\nUSER FEEDBACK:\n{user_feedback}\n\nGenerate a refined research plan."
    else:
        system_prompt = f"""You are a research strategist. Create a **5-point action-oriented research plan** for the given topic.
Each goal MUST start with: [RESEARCH] or [DELIVERABLE]. RESEARCH goals start with verbs like 'Analyze', 'Identify', 'Investigate'.
DELIVERABLE goals describe synthesis/output artifacts. Keep each goal concise (1-2 sentences).

CRITICAL: Include at least 1-2 [DELIVERABLE] goals. These are synthesis artifacts (comparison matrices, decision frameworks,
ranked lists, summary tables) built from the research findings. A plan with only [RESEARCH] goals is INCOMPLETE.

Current date: {today}"""
        user_prompt = f"Research topic: {topic}\n\nGenerate a research plan."

    response = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
    return response.content.strip()


def _generate_sections(plan: str, llm: Any | None = None) -> str:
    """Call the LLM to produce a markdown report outline from the plan."""
    if llm is None:
        llm = _get_llm()
    system_prompt = "You are an expert report architect. Create a markdown outline with 4-6 distinct sections. Do NOT include References or Sources."
    response = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=f"Research Plan:\n{plan}")])
    return response.content.strip()


def _extract_research_goals(plan: str) -> list[str]:
    """Extract [RESEARCH] goals from the plan for parallel fan-out via Send()."""
    goals = re.findall(r"\[RESEARCH\]\s*(.+?)(?=\n\[|\Z|\n\n)", plan, re.DOTALL)
    return [g.strip() for g in goals if g.strip()]


def planner_node(state: ResearchState) -> dict:
    """Generate research plan, extract parallel goals.

    Plan approval happens OUTSIDE the graph (two-pass approach via
    generate_plan_only + pre-populated state). This avoids LangGraph
    interrupt() double-entry issues and saves one LLM call.
    """
    topic = state.get("topic", "")
    if not topic:
        return {"errors": ["No topic provided"]}

    previous_plan = state.get("research_plan")
    plan_approved = state.get("plan_approved", False)

    # If already approved with a plan, pass through
    if plan_approved and previous_plan:
        logger.info("Plan already approved — skipping planner")
        return {}

    llm = _get_llm()
    plan = _generate_plan(topic, previous_plan, state.get("user_feedback"), llm=llm)
    sections = _generate_sections(plan, llm=llm)
    goals = _extract_research_goals(plan)

    # Guarantee at least one DELIVERABLE goal
    if "[DELIVERABLE]" not in plan:
        plan += (
            f"\n[DELIVERABLE] Synthesize all findings into a structured summary "
            f"with key takeaways, ranked recommendations, and a decision matrix "
            f"where applicable."
        )
        logger.info("Added default DELIVERABLE goal to plan")

    logger.info("Plan: %d chars | Sections: %d chars | Goals: %d", len(plan), len(sections), len(goals))

    return {
        "research_plan": plan,
        "report_sections": sections,
        "plan_approved": False,
        "parallel_goals": goals,
        **llm.token_delta(),
    }


def generate_plan_only(topic: str, previous_plan: str | None = None,
                       user_feedback: str | None = None) -> dict:
    """Generate a research plan without graph/interrupt. For two-pass CLI flow.

    Returns dict with research_plan, report_sections, parallel_goals.
    No graph needed — direct LLM calls only.
    """
    llm = _get_llm()
    plan = _generate_plan(topic, previous_plan, user_feedback, llm=llm)
    sections = _generate_sections(plan, llm=llm)

    # Guarantee at least one DELIVERABLE goal
    if "[DELIVERABLE]" not in plan:
        plan += (
            "\n[DELIVERABLE] Synthesize all findings into a structured summary "
            "with key takeaways, ranked recommendations, and a decision matrix "
            "where applicable."
        )

    goals = _extract_research_goals(plan)
    logger.info("Plan generated: %d chars, %d sections, %d research goals", len(plan), len(sections), len(goals))

    return {
        "research_plan": plan,
        "report_sections": sections,
        "parallel_goals": goals,
        **llm.token_delta(),
    }
