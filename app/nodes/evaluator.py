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


def _extract_scores(comment: str, iteration: int) -> dict | None:
    """Parse numeric scores from evaluator comment for stagnation detection.

    Expected format: "Scores: source_quality=4/5, claim_verification=3/5, completeness=4/5. ..."

    Returns dict with iteration + scores, or None if parsing fails.
    """
    import re
    sq = re.search(r"source_quality=(\d+)/5", comment)
    cv = re.search(r"claim_verification=(\d+)/5", comment)
    cp = re.search(r"completeness=(\d+)/5", comment)
    if sq and cv and cp:
        return {
            "iteration": iteration,
            "source_quality": int(sq.group(1)),
            "claim_verification": int(cv.group(1)),
            "completeness": int(cp.group(1)),
        }
    return None


def _get_llm() -> Any:
    """Get the chat model for evaluation.

    Warns if critic model matches worker model — same-model evaluation
    produces inflated scores (LLMs grading their own output).
    """
    from app.tokens import get_llm

    if config.critic_model == config.worker_model:
        logger.warning(
            "CRITIC_MODEL (%s) matches WORKER_MODEL — evaluation quality degraded. "
            "Set CRITIC_MODEL to a stronger model (deepseek-v4-pro, claude-sonnet-4, gpt-4o).",
            config.critic_model,
        )

    return get_llm(model=config.critic_model, temperature=0.1,
                   api_key=config.critic_api_key or config.worker_api_key or None,
                   base_url=config.critic_api_base or config.worker_api_base or None, node_name="evaluator")


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


def _rule_based_evaluation(findings: str, topic: str) -> Feedback | None:
    """Quick heuristic evaluation to skip LLM call for obvious pass/fail cases.

    Returns PASS or FAIL feedback if findings are clearly good/bad.
    Returns None if ambiguous — fall through to LLM evaluator.

    Heuristics (tuned to be conservative — when in doubt, let LLM decide):
    - CLEAR FAIL: 0 URLs, <200 chars, or contains error keywords
    - CLEAR PASS: 3+ URLs, 1+ numbers/dates, structured sections, >1000 chars
    - AMBIGUOUS: everything else
    """
    if not findings or len(findings) < 200:
        return Feedback(
            grade="fail",
            comment="Rule-based pre-check: findings too short (<200 chars). Scores: source_quality=1/5, claim_verification=1/5, completeness=1/5. Insufficient content for evaluation.",
            follow_up_queries=[
                SearchQuery(search_query=f"{topic} comprehensive overview"),
                SearchQuery(search_query=f"{topic} recent developments"),
                SearchQuery(search_query=f"{topic} key statistics data"),
            ],
        )

    # Count URLs
    urls = re.findall(r"https?://[^\s\)\"\'>]+", findings)
    url_count = len(urls)

    # Check for numbers/dates (quantitative data)
    has_numbers = bool(re.search(r"\b\d{1,3}(,\d{3})*(\.\d+)?\b", findings))  # numbers
    has_dates = bool(re.search(r"\b20\d{2}\b", findings))  # years 2000-2099
    has_percentages = bool(re.search(r"\d+%", findings))
    has_quantitative = has_numbers or has_dates or has_percentages

    # Check for structure (## headers indicate sections)
    has_structure = bool(re.search(r"^##?\s+\w", findings, re.MULTILINE))

    # Check for error keywords
    error_keywords = ["failed", "no results", "error", "could not", "unable to", "search failed"]
    has_errors = any(kw in findings.lower() for kw in error_keywords)

    # CLEAR FAIL: no URLs, or has explicit errors, or very short
    if url_count == 0 or has_errors:
        follow_ups = [
            SearchQuery(search_query=f"{topic} authoritative sources"),
            SearchQuery(search_query=f"{topic} official documentation"),
            SearchQuery(search_query=f"{topic} research paper"),
            SearchQuery(search_query=f"{topic} statistics data"),
        ]
        return Feedback(
            grade="fail",
            comment=f"Rule-based pre-check: {'no citations found' if url_count == 0 else 'errors detected in findings'}. Scores: source_quality=1/5, claim_verification=2/5, completeness=2/5. Needs re-research.",
            follow_up_queries=follow_ups,
        )

    # CLEAR PASS: substantial, structured, cited, quantitative
    if url_count >= 3 and has_quantitative and has_structure and len(findings) > 400:
        return Feedback(
            grade="pass",
            comment=f"Rule-based pre-check: {url_count} citations, structured sections, quantitative data, substantial length. Scores: source_quality=4/5, claim_verification=4/5, completeness=4/5. Meets threshold without LLM evaluation.",
            follow_up_queries=None,
        )

    # Ambiguous — fall through to LLM
    return None


def research_evaluator_node(state: ResearchState) -> dict:
    """Critique the research findings and produce a structured Feedback evaluation.

    Uses JSON prompting instead of ``with_structured_output`` for model
    compatibility. Graceful degradation on parse failure.

    Rule-based pre-check skips LLM call for obvious pass/fail cases.
    Configurable via ENABLE_EVALUATOR env var (default: true).
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

    # If evaluator disabled, always pass
    if not config.enable_evaluator:
        logger.info("Evaluator disabled via ENABLE_EVALUATOR — auto-passing")
        print("  ⚠️  Evaluator disabled — auto-pass", flush=True)
        return {
            "research_evaluation": Feedback(
                grade="pass",
                comment="Evaluator disabled via configuration. Auto-pass.",
                follow_up_queries=None,
            )
        }

    # Rule-based pre-check: skip LLM for obvious cases
    pre_check = _rule_based_evaluation(findings, topic)
    if pre_check:
        emoji = "✅" if pre_check.grade == "pass" else "❌"
        source = "rule-based pre-check"
        print(f"  {emoji} Evaluation ({source}): {pre_check.grade.upper()} — {pre_check.comment[:80]}", flush=True)
        logger.info("Evaluator skipped LLM call — %s determined %s", source, pre_check.grade)

        scores_entry = _extract_scores(pre_check.comment, state.get("iteration_count", 0))
        return {
            "research_evaluation": pre_check,
            "evaluation_scores": [scores_entry] if scores_entry else [],
        }

    # Fall through to LLM-based evaluation for ambiguous cases
    try:
        llm = _get_llm()

        system_prompt = f"""You are a meticulous quality assurance analyst evaluating research findings. 
You have ONE job: catch weak research BEFORE it reaches the final report.

BE STRICT. A FAIL now costs a 30-second re-search loop. A weak report costs credibility.

Research topic: {topic}

EVALUATION RUBRIC:

1. SOURCE QUALITY (score 1-5):
   - Does the research cite specific sources with URLs? (Not vague "according to experts")
   - Are at least 40% of sources from authoritative domains? (official docs, GitHub repos, arxiv, research papers)
   - Are sources recent? (within 1 year unless citing foundational/evergreen references)
   - Deductions: no citations = score 1, only search snippets = score 2, vendor blogs only = score 3

2. CLAIM VERIFICATION (score 1-5):
   - Are factual claims backed by citations?
   - Do numbers/dates/statistics have sources?
   - Is there evidence the researcher actually READ the sources, not just search snippets?
   - Deductions: unsupported claims = score 1, just paraphrased abstracts = score 3

3. COMPLETENESS (score 1-5):
   - Does the research cover ALL major angles of the topic?
   - Are there obvious gaps or missing perspectives?
   - Is it deep or shallow? (deep = specific findings, shallow = generic summaries)
   - Deductions: one-sided = score 1, missing key aspect = score 2

4. CONTRADICTIONS (bonus check):
   - Does any section contradict another?
   - Are conflicting sources acknowledged?

GRADING RULES:
- GRADE "pass" ONLY IF: all three scores ≥4, at least 3 specific citations with URLs, at least 1 quantitative finding (number, percentage, date, statistic)
- GRADE "fail" for anything less
- If FAIL, generate 5-7 specific follow-up queries that would fix the weakest areas

You MUST respond with a valid JSON object ONLY:
{{
  "grade": "pass" or "fail",
  "comment": "Scores: source_quality=X/5, claim_verification=Y/5, completeness=Z/5. [detailed justification]",
  "follow_up_queries": [
    {{"search_query": "specific follow-up query 1"}},
    {{"search_query": "specific follow-up query 2"}}
  ]
}}

OK grade "pass": only if all scores ≥4, 3+ URL citations present, 1+ quantitative finding.
Else grade "fail": with 5-7 follow_up_queries.
follow_up_queries MUST be null/empty if grade is "pass"."""

        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Research Findings to evaluate:\n\n{findings}\n\nApply the rubric. Be strict. Return JSON only."),
        ])

        evaluation = _parse_feedback_json(response.content)

        if evaluation:
            logger.info("Evaluation: %s — %s", evaluation.grade, evaluation.comment[:80])

            emoji = "✅" if evaluation.grade == "pass" else "❌"
            print(f"  {emoji} Evaluation: {evaluation.grade.upper()} — {evaluation.comment[:100]}", flush=True)

            # Extract scores from comment for stagnation detection
            scores_entry = _extract_scores(evaluation.comment, state.get("iteration_count", 0))

            return {
                "research_evaluation": evaluation,
                "evaluation_scores": [scores_entry] if scores_entry else [],
                **llm.token_delta(),
            }
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
