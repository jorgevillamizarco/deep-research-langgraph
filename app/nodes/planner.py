"""Planner node — plan generation and section outlining.

Replicates ADK's ``plan_generator`` and ``section_planner`` agents.
Two LLM calls in sequence:
1. Plan generator: 5 action-oriented research goals with [RESEARCH]/[DELIVERABLE] tags
2. Section planner: Markdown report outline with 4-6 sections

If ``user_feedback`` exists in state, refines the existing plan with
[MODIFIED]/[NEW]/[IMPLIED] tags.

Uses ``interrupt()`` for human-in-the-loop plan approval. When resumed,
checks for ``plan_approved`` or ``user_feedback`` from the Command(resume=...)
payload.
"""

from __future__ import annotations

import datetime
import logging
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
        system_prompt = f"""You are a research strategist. You have an existing research plan and user feedback.
Improve the plan based on the feedback. Mark changes with:
- [MODIFIED] — changed wording, scope, or source strategy
- [NEW] — added at user's request
- [IMPLIED] — proactively added because existing goals imply a deliverable
- [REMOVED] — removed per user request

Maintain the original sequential order of existing bullet points.
Current date: {today}"""
        user_prompt = f"""TOPIC: {topic}

EXISTING PLAN:
{previous_plan}

USER FEEDBACK:
{user_feedback}

Generate a refined research plan."""
    else:
        system_prompt = f"""You are a research strategist. Create a **5-point action-oriented research plan** for the given topic.

Each goal MUST start with a task type prefix:
- **[RESEARCH]** — information gathering, investigation, analysis, data collection. Start with verbs like 'Analyze', 'Identify', 'Investigate'.
- **[DELIVERABLE]** — synthesizing collected information, creating structured outputs (tables, summaries, reports).

After the 5 RESEARCH goals, if any imply standard deliverables (e.g., comparative analysis → comparison table, comprehensive review → summary document), add them as [DELIVERABLE][IMPLIED].

Keep each goal concise (1-2 sentences).
Current date: {today}"""
        user_prompt = f"Research topic: {topic}\n\nGenerate a research plan."

    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])
    return response.content.strip()


def _generate_sections(plan: str) -> str:
    """Call the LLM to produce a markdown report outline from the plan."""
    llm = _get_llm()

    system_prompt = """You are an expert report architect. Using the research plan below, design a logical structure for the final report.

Create a markdown outline with 4-6 distinct sections that cover the topic comprehensively without overlap.

Use any markdown format you prefer.

IMPORTANT: Do NOT include a "References" or "Sources" section. Citations will be handled in-line."""

    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Research Plan:\n{plan}"),
    ])
    return response.content.strip()


def planner_node(state: ResearchState) -> dict:
    """Generate research plan and section outline, then interrupt for human approval.

    The interrupt pauses graph execution and presents the plan to the user.
    When resumed via ``Command(resume=...)``:
    - ``{"plan_approved": True}`` → plan is approved, proceed to research
    - ``{"user_feedback": "feedback text"}`` → regenerate plan with feedback
    """
    topic = state.get("topic", "")
    if not topic:
        return {"errors": ["No topic provided"]}

    previous_plan = state.get("research_plan")
    user_feedback = state.get("user_feedback")
    plan_approved = state.get("plan_approved", False)

    # If already approved, skip everything
    if plan_approved and previous_plan:
        logger.info("Plan already approved — skipping planner")
        return {}

    # Generate or refine the plan
    plan = _generate_plan(topic, previous_plan, user_feedback)
    sections = _generate_sections(plan)

    logger.info("Plan generated (%d chars), sections (%d chars)", len(plan), len(sections))

    # Interrupt for human review — this pauses the graph
    # The CLI will display the plan and ask for approval
    # The return value of interrupt() is whatever is passed in Command(resume=...)
    resume_value = interrupt({
        "question": "Review the research plan below. Approve to proceed or provide feedback.",
        "research_plan": plan,
        "report_sections": sections,
        "topic": topic,
    })

    # After resume, check what the user decided
    if isinstance(resume_value, dict):
        if resume_value.get("plan_approved"):
            logger.info("Plan approved by user")
            return {
                "research_plan": plan,
                "report_sections": sections,
                "plan_approved": True,
                "user_feedback": None,
            }
        elif resume_value.get("user_feedback"):
            feedback = resume_value["user_feedback"]
            logger.info("User provided feedback: %s", feedback[:80])
            # Keep the plan but mark for refinement on next planner run
            return {
                "research_plan": plan,
                "report_sections": sections,
                "plan_approved": False,
                "user_feedback": feedback,
            }

    # Fallback: treat as feedback
    return {
        "research_plan": plan,
        "report_sections": sections,
        "plan_approved": False,
        "user_feedback": None,
    }
