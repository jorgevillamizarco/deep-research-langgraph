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
from langgraph.types import interrupt

from app.config import config
from app.state import ResearchState

logger = logging.getLogger(__name__)


def _get_llm() -> Any:
    """Get the chat model for planning (uses worker_model from config)."""
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=config.worker_model,
        temperature=0.1,
        api_key=config.worker_api_key or None,
        base_url=config.worker_api_base or None,
    )


def _generate_plan(topic: str, previous_plan: str | None, user_feedback: str | None) -> str:
    """Call the LLM to generate or refine a research plan."""
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


def _generate_sections(plan: str) -> str:
    """Call the LLM to produce a markdown report outline from the plan."""
    llm = _get_llm()
    system_prompt = "You are an expert report architect. Create a markdown outline with 4-6 distinct sections. Do NOT include References or Sources."
    response = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=f"Research Plan:\n{plan}")])
    return response.content.strip()


def _extract_research_goals(plan: str) -> list[str]:
    """Extract [RESEARCH] goals from the plan for parallel fan-out via Send()."""
    goals = re.findall(r"\[RESEARCH\]\s*(.+?)(?=\n\[|\Z|\n\n)", plan, re.DOTALL)
    return [g.strip() for g in goals if g.strip()]


def planner_node(state: ResearchState) -> dict:
    """Generate research plan, extract parallel goals, interrupt for human approval."""
    topic = state.get("topic", "")
    if not topic:
        return {"errors": ["No topic provided"]}

    previous_plan = state.get("research_plan")
    user_feedback = state.get("user_feedback")
    plan_approved = state.get("plan_approved", False)

    # If already approved with a plan, pass through
    if plan_approved and previous_plan:
        logger.info("Plan already approved — skipping planner")
        return {}

    # If resuming from interrupt with approval but no plan in state yet,
    # regenerate (the plan text was in the interrupt payload, lost on resume)
    if plan_approved and not previous_plan:
        logger.info("Plan approved on resume — regenerating with same prompt")
        # Fall through to regenerate — prompt includes DELIVERABLE mandate

    plan = _generate_plan(topic, previous_plan, user_feedback)
    sections = _generate_sections(plan)
    goals = _extract_research_goals(plan)

    logger.info("Plan: %d chars | Sections: %d chars | Goals: %d", len(plan), len(sections), len(goals))

    resume_value = interrupt({
        "question": "Review the research plan below. Approve to proceed or provide feedback.",
        "research_plan": plan,
        "report_sections": sections,
        "topic": topic,
    })

    if isinstance(resume_value, dict):
        if resume_value.get("plan_approved"):
            # Use plan from resume value if passed (avoids regeneration on auto-approve)
            approved_plan = resume_value.get("research_plan", plan)
            approved_sections = resume_value.get("report_sections", sections)
            # Re-extract goals from the original plan (may differ from regenerated)
            if resume_value.get("research_plan"):
                goals = _extract_research_goals(approved_plan)
            logger.info("Plan approved — %d parallel goals for fan-out", len(goals))
            return {
                "research_plan": approved_plan,
                "report_sections": approved_sections,
                "plan_approved": True,
                "user_feedback": None,
                "parallel_goals": goals,
            }
        elif resume_value.get("user_feedback"):
            feedback = resume_value["user_feedback"]
            logger.info("User feedback: %s", feedback[:80])
            return {
                "research_plan": plan,
                "report_sections": sections,
                "plan_approved": False,
                "user_feedback": feedback,
                "parallel_goals": goals,
            }

    return {
        "research_plan": plan,
        "report_sections": sections,
        "plan_approved": False,
        "user_feedback": None,
        "parallel_goals": goals,
    }
