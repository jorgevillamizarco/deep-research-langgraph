"""Evaluator node — quality critique with structured Feedback output.

Replicates ADK's ``research_evaluator`` agent. Uses JSON prompting instead of
``with_structured_output`` for broader model compatibility (DeepSeek V4, etc.).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import config
from app.state import Feedback, ResearchState, SearchQuery

logger = logging.getLogger(__name__)


def _get_llm() -> Any:
    """Get the chat model for evaluation."""
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=config.critic_model,
        temperature=0.1,
        api_key=config.critic_api_key or config.worker_api_key or None,
        base_url=config.critic_api_base or config.worker_api_base or None,
    )


def _parse_feedback_json(text: str) -> Feedback | None:
    """Parse JSON from LLM response, handling markdown fences and partial output."""
    # Try to extract JSON from markdown code blocks first
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    raw = json_match.group(1) if json_match else text.strip()

    # Find JSON object boundaries
    brace_start = raw.find("{")
    brace_end = raw.rfind("}")
    if brace_start >= 0 and brace_end > brace_start:
        raw = raw[brace_start : brace_end + 1]

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Failed to parse evaluator JSON: %s", raw[:200])
        return None

    # Validate required fields
    grade = data.get("grade")
    if grade not in ("pass", "fail"):
        logger.warning("Invalid grade in evaluator response: %s", grade)
        return None

    comment = data.get("comment", "No comment provided")

    follow_ups = None
    queries_raw = data.get("follow_up_queries")
    if queries_raw and isinstance(queries_raw, list):
        follow_ups = [
            SearchQuery(search_query=q.get("search_query", str(q)))
            for q in queries_raw
        ]

    return Feedback(
        grade=grade,
        comment=comment,
        follow_up_queries=follow_ups,
    )


def research_evaluator_node(state: ResearchState) -> dict:
    """Critique the research findings and produce a structured FeedbacK evaluation.

    Uses JSON prompting instead of ``with_structured_output`` for model
    compatibility. Graceful degradation on parse failure.
    """
    findings = state.get("section_research_findings")
    topic = state.get("topic", "")

    if not findings:
        return {
            "research_evaluation": Feedback(
                grade="fail",
                comment="No research findings to evaluate.",
                follow_up_queries=None,
            )
        }

    try:
        llm = _get_llm()

        system_prompt = f"""You are a meticulous quality assurance analyst evaluating research findings.

CRITICAL RULES:
1. Assume the given research topic is correct. Do not question the subject itself.
2. Your ONLY job is to assess the quality, depth, and completeness of the research.
3. Focus on: comprehensiveness, use of credible sources with citations, depth of analysis, clarity.
4. Do NOT fact-check the premise or timeline.
5. If suggesting follow-up queries, they should dive deeper into the existing topic.

Topic: {topic}

You MUST respond with a valid JSON object ONLY, no other text:
{{
  "grade": "pass" or "fail",
  "comment": "Detailed explanation of the evaluation, highlighting strengths and weaknesses",
  "follow_up_queries": [
    {{"search_query": "specific follow-up query 1"}},
    {{"search_query": "specific follow-up query 2"}}
  ]
}}

- Set grade "pass" if research is thorough, well-sourced, and covers the topic.
- Set grade "fail" if significant gaps exist in depth or coverage, with 5-7 follow_up_queries.
- follow_up_queries should be null/empty if grade is "pass"."""

        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Research Findings:\n{findings}"),
        ])

        evaluation = _parse_feedback_json(response.content)

        if evaluation:
            logger.info("Evaluation: %s — %s", evaluation.grade, evaluation.comment[:80])
            return {"research_evaluation": evaluation}
        else:
            # Fallback: return a fail with generic comment
            logger.warning("Could not parse evaluator response, returning fail")
            return {
                "research_evaluation": Feedback(
                    grade="fail",
                    comment="Could not parse evaluation result. Please review findings manually.",
                    follow_up_queries=None,
                ),
                "errors": state.get("errors", []) + ["Evaluator parse failure"],
            }

    except Exception as e:
        logger.error("Evaluator LLM call failed: %s", e)
        return {
            "research_evaluation": Feedback(
                grade="fail",
                comment=f"Evaluation failed: {e}",
                follow_up_queries=None,
            ),
            "errors": state.get("errors", []) + [f"Evaluator error: {e}"],
        }
