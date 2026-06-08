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
from app.models import ReportBlueprint, ReportSectionSpec, ReportTemplate
from app.state import ResearchState

logger = logging.getLogger(__name__)


def _get_llm() -> Any:
    """Get the chat model for planning (uses worker_model from config)."""
    from app.tokens import get_llm
    return get_llm(model=config.worker_model, temperature=0.1,
                   api_key=config.worker_api_key or None,
                   base_url=config.worker_api_base or None, node_name="planner")


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

DOMAIN DISAMBIGUATION: If the topic mentions terms with multiple meanings across different domains
(e.g., "PRR" could be DoD manufacturing review or software production readiness review, "pipeline" could be CI/CD or data processing),
add at least one RESEARCH goal that explicitly investigates the term in the context of the topic's domain.
For example: "[RESEARCH] Investigate how Production Readiness Review (PRR) is applied in software engineering contexts."

JURISDICTION-SPECIFIC TOPICS: If the enrichment brief identifies a specific country, legal system, or language region,
you MUST annotate EVERY [RESEARCH] goal with the search language and key domains in parentheses at the end.
Format: "(search in LANGUAGE; sources: domain1, domain2, ...)"
Example: "[RESEARCH] Analyze recent Tribunal Supremo rulings on nationality by residence under RD 1155/2024 (search in Spanish; sources: boe.es, poderjudicial.es, noticiasjuridicas.com, law firm blogs in Spanish)."
Failure to annotate jurisdiction-specific goals will result in research queries in the wrong language and unusable results.

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


def select_report_template(topic: str) -> ReportTemplate:
    """Choose a report template using simple topic heuristics."""
    lowered = topic.lower()

    if any(term in lowered for term in ("should i invest", "ipo", "stock", "retail investor")):
        return "retail_investor_memo"
    if any(term in lowered for term in ("should we choose", "should we build", "should we adopt")):
        return "decision_memo"
    if any(term in lowered for term in ("architecture", "system design", "agent architecture", "design improvement")):
        return "architecture_review"
    if any(term in lowered for term in ("compare", "best ", "rank", "versus", "vs ")):
        return "compare_and_recommend"
    if any(term in lowered for term in ("law", "legal", "regulatory", "jurisdiction", "visa", "immigration", "tax")):
        return "legal_policy_brief"
    return "generic_research_report"


def _default_sections_for_template(template: ReportTemplate) -> list[ReportSectionSpec]:
    """Deterministic starter sections for each report template."""
    sections_by_template: dict[ReportTemplate, list[tuple[str, str]]] = {
        "generic_research_report": [
            ("Executive Summary", "Answer the question directly and summarize major findings."),
            ("Key Findings", "Present the most important evidence and themes."),
            ("Gaps & Uncertainties", "Disclose missing evidence and unresolved issues."),
        ],
        "decision_memo": [
            ("Executive Summary", "State the decision and the recommendation."),
            ("What Is Being Decided", "Clarify the actual choice and constraints."),
            ("Options & Tradeoffs", "Compare realistic options and tradeoffs."),
            ("Recommendation", "Give a direct recommendation with caveats."),
        ],
        "retail_investor_memo": [
            ("Executive Summary", "State the invest / do-not-invest answer and why."),
            ("What Is Being Decided", "Clarify the security, entry point, and investor exposure."),
            ("Business & Economics", "Explain how the business works and key drivers."),
            ("Valuation Scenarios", "Lay out bear/base/bull scenarios and assumptions."),
            ("Retail Investor Checklist", "Give a go/no-go checklist for a retail investor."),
            ("Recommendation", "State the recommendation and main caveats."),
        ],
        "architecture_review": [
            ("Executive Summary", "Summarize the architecture recommendation."),
            ("Current Architecture", "Describe the current system and constraints."),
            ("Options & Tradeoffs", "Compare plausible improvements and tradeoffs."),
            ("Implementation Roadmap", "Lay out the practical implementation sequence."),
            ("Recommendation", "State the preferred path and why."),
        ],
        "compare_and_recommend": [
            ("Executive Summary", "State the best option and why."),
            ("Comparison Matrix", "Compare options against key criteria."),
            ("Scoring Rationale", "Explain the weighting and judgment."),
            ("Recommendation", "State the recommendation and caveats."),
        ],
        "legal_policy_brief": [
            ("Question Presented", "State the legal or policy question precisely."),
            ("Controlling Authorities", "Identify the highest-authority sources."),
            ("Ambiguities", "Explain unresolved ambiguity and conflicting interpretations."),
            ("Practical Answer", "Give the actionable answer with caveats."),
        ],
    }
    return [ReportSectionSpec(title=title, purpose=purpose) for title, purpose in sections_by_template[template]]


def _sections_to_markdown(sections: list[ReportSectionSpec]) -> str:
    return "\n".join(f"## {section.title}" for section in sections)


def build_report_blueprint(topic: str, plan: str, sections_markdown: str | None = None) -> ReportBlueprint:
    """Create a deterministic report blueprint from topic and plan."""
    template = select_report_template(topic)
    audience = "general"
    decision_context = topic.strip()
    required_tables: list[str] = []
    required_scenarios: list[str] = []
    required_decision_artifacts: list[str] = []
    source_requirements: list[str] = []

    if template == "retail_investor_memo":
        audience = "retail investor"
        required_tables = ["key_facts_table", "risk_table"]
        required_scenarios = ["bear", "base", "bull"]
        required_decision_artifacts = ["decision_checklist", "recommendation_block"]
        source_requirements = ["official filings", "reputable financial reporting"]
    elif template == "architecture_review":
        audience = "engineering leadership"
        required_tables = ["options_tradeoff_table"]
        required_decision_artifacts = ["implementation_roadmap", "recommendation_block"]
        source_requirements = ["primary technical docs", "implementation examples"]
    elif template == "decision_memo":
        audience = "decision maker"
        required_tables = ["options_table"]
        required_decision_artifacts = ["scenario_table", "recommendation_block"]
    elif template == "compare_and_recommend":
        required_tables = ["comparison_matrix"]
        required_decision_artifacts = ["recommendation_block"]
    elif template == "legal_policy_brief":
        audience = "policy or legal reader"
        source_requirements = ["controlling authorities", "jurisdiction-specific sources"]

    section_specs = _default_sections_for_template(template)
    if template == "generic_research_report" and sections_markdown and sections_markdown.strip():
        parsed_titles = [
            line.strip().lstrip("#").strip()
            for line in sections_markdown.splitlines()
            if line.strip().startswith("##")
        ]
        if parsed_titles:
            section_specs = [ReportSectionSpec(title=title, purpose="Planned report section.") for title in parsed_titles]

    return ReportBlueprint(
        audience=audience,
        decision_context=decision_context,
        template=template,
        sections=section_specs,
        required_tables=required_tables,
        required_scenarios=required_scenarios,
        required_decision_artifacts=required_decision_artifacts,
        source_requirements=source_requirements,
    )


def generate_blueprint_and_sections(topic: str, plan: str, sections_markdown: str | None = None) -> tuple[ReportBlueprint, str]:
    """Build a blueprint and ensure markdown report sections exist."""
    blueprint = build_report_blueprint(topic, plan, sections_markdown)
    if blueprint.template == "generic_research_report" and sections_markdown and sections_markdown.strip():
        normalized_sections = sections_markdown.strip()
    else:
        normalized_sections = _sections_to_markdown(blueprint.sections)
    return blueprint, normalized_sections


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
    blueprint, sections = generate_blueprint_and_sections(topic, plan, sections)
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
        "report_blueprint": blueprint.model_dump(),
        "plan_approved": False,
        "parallel_goals": goals,
        **llm.token_delta(),
    }


def enrich_topic(topic: str, llm: Any | None = None) -> str:
    """Enrich a raw user topic into a structured research brief.

    Adds domain signals, ambiguity detection, expected output formats,
    and key dimensions — so the planner generates better goals and the
    researcher knows what to look for.

    Args:
        topic: Raw user topic (e.g., "compare software assessment frameworks")
        llm: Optional LLM instance (creates one if not provided)

    Returns:
        Enriched research brief with domain context, disambiguation notes,
        and output expectations. Original topic is preserved as a prefix.
    """
    if llm is None:
        llm = _get_llm()

    system_prompt = """You are a research methodologist. Given a research topic, produce a structured brief
that helps downstream agents plan better research. Identify domain context,
potential ambiguities, jurisdiction/language requirements, and what a good answer looks like.

Return ONLY the brief text. Do NOT include preamble or explanation."""

    user_prompt = f"""Research topic: {topic}

Produce a structured research brief covering:

1. DOMAIN: What field/domain does this belong to? Be specific.
2. AMBIGUITIES: Are there terms with multiple meanings across domains?
   (e.g., "PRR" = manufacturing review vs software readiness review,
   "pipeline" = CI/CD vs data processing vs sales)
3. JURISDICTION & LANGUAGE: Is this topic tied to a specific country, legal system,
   or language region? If so, what language should search queries use?
   (e.g., "Spanish immigration law" → search in Spanish on .es domains,
   "German tax code" → search in German on .de domains,
   "French labor law" → search in French). Be explicit.
4. EXPECTED OUTPUT: What format should the final answer take?
   (comparison matrix, ranked list, decision framework, narrative analysis)
5. KEY DIMENSIONS: What specific attributes or axes should be compared/analyzed?
6. SOURCE DIVERSITY: What types of sources are needed?
   (official standards, academic papers, engineering blogs, vendor docs,
   government gazettes, legal databases, local-language law firm analyses)

Be concise but specific. The planner will use this to generate better research goals."""

    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])
    enrichment = response.content.strip()

    # Combine: original topic + enriched brief
    brief = f"TOPIC: {topic}\n\nRESEARCH BRIEF:\n{enrichment}"
    logger.info("Enriched topic (%d chars raw → %d chars brief)", len(topic), len(brief))
    return brief


def generate_plan_only(topic: str, previous_plan: str | None = None,
                       user_feedback: str | None = None,
                       enriched: bool = True) -> dict:
    """Generate a research plan without graph/interrupt. For two-pass CLI flow.

    Returns dict with research_plan, report_sections, parallel_goals.
    No graph needed — direct LLM calls only.

    Args:
        enriched: If True, enrich the raw topic with domain context and
                  disambiguation before generating the plan.
    """
    llm = _get_llm()

    # Enrich the topic before planning (if not a refinement/feedback cycle)
    research_topic = topic
    if enriched and not previous_plan:
        research_topic = enrich_topic(topic, llm=llm)

    plan = _generate_plan(research_topic, previous_plan, user_feedback, llm=llm)
    sections = _generate_sections(plan, llm=llm)
    blueprint, sections = generate_blueprint_and_sections(topic, plan, sections)

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
        "report_blueprint": blueprint.model_dump(),
        "parallel_goals": goals,
        **llm.token_delta(),
    }
