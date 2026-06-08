"""Tests for the LangGraph deep research agent."""

from __future__ import annotations

from app.agent import build_research_graph, build_refinement_subgraph
from app.state import Feedback, ResearchState, SearchQuery


def test_build_refinement_subgraph():
    """The refinement subgraph compiles without errors."""
    subgraph = build_refinement_subgraph()
    assert subgraph is not None


def test_build_research_graph():
    """The main research graph compiles without errors."""
    graph = build_research_graph()
    assert graph is not None


def test_route_after_evaluation_pass():
    """Pass evaluation routes to 'pass'."""
    from app.agent import route_after_evaluation

    state: ResearchState = {
        "topic": "test",
        "plan_approved": True,
        "research_plan": None,
        "report_sections": None,
        "section_research_findings": "Some findings",
        "research_evaluation": Feedback(
            grade="pass",
            comment="Looks good",
            follow_up_queries=None,
        ),
        "research_iteration": 1,
        "url_to_short_id": {},
        "sources": {},
        "final_cited_report": None,
        "final_report_with_citations": None,
        "messages": [],
        "iteration_count": 1,
        "max_iterations": 5,
        "user_feedback": None,
        "errors": [],
    }

    result = route_after_evaluation(state)
    assert result == "pass", f"Expected 'pass', got {result!r}"


def test_route_after_evaluation_fail():
    """Fail evaluation with remaining iterations routes to 'enhancer'."""
    from app.agent import route_after_evaluation

    state: ResearchState = {
        "topic": "test",
        "plan_approved": True,
        "research_plan": None,
        "report_sections": None,
        "section_research_findings": "Some findings",
        "research_evaluation": Feedback(
            grade="fail",
            comment="Need more depth",
            follow_up_queries=[SearchQuery(search_query="more info")],
        ),
        "research_iteration": 1,
        "url_to_short_id": {},
        "sources": {},
        "final_cited_report": None,
        "final_report_with_citations": None,
        "messages": [],
        "iteration_count": 1,
        "max_iterations": 5,
        "user_feedback": None,
        "errors": [],
    }

    result = route_after_evaluation(state)
    assert result == "enhancer", f"Expected 'enhancer', got {result!r}"


def test_route_after_evaluation_max_iterations():
    """Max iterations reached routes to 'pass' even if grade is fail."""
    from app.agent import route_after_evaluation

    state: ResearchState = {
        "topic": "test",
        "plan_approved": True,
        "research_plan": None,
        "report_sections": None,
        "section_research_findings": "Some findings",
        "research_evaluation": Feedback(
            grade="fail",
            comment="Still not good enough",
            follow_up_queries=[SearchQuery(search_query="more info")],
        ),
        "research_iteration": 5,
        "url_to_short_id": {},
        "sources": {},
        "final_cited_report": None,
        "final_report_with_citations": None,
        "messages": [],
        "iteration_count": 5,
        "max_iterations": 5,
        "user_feedback": None,
        "errors": [],
    }

    result = route_after_evaluation(state)
    assert result == "pass", f"Expected 'pass' (max iterations), got {result!r}"


def test_empty_findings_evaluator():
    """Evaluator handles missing findings gracefully."""
    from app.nodes.evaluator import research_evaluator_node

    state: ResearchState = {
        "topic": "test",
        "plan_approved": True,
        "research_plan": "Some plan",
        "report_sections": "Sections",
        "section_research_findings": None,
        "research_evaluation": None,
        "research_iteration": 0,
        "url_to_short_id": {},
        "sources": {},
        "final_cited_report": None,
        "final_report_with_citations": None,
        "messages": [],
        "iteration_count": 0,
        "max_iterations": 5,
        "user_feedback": None,
        "errors": [],
    }

    result = research_evaluator_node(state)
    eval_result = result.get("research_evaluation")
    assert eval_result is not None
    assert eval_result.grade == "fail"


def test_extract_citations():
    """Citation extraction parses markdown links."""
    from app.tools.citations import extract_citations_from_content

    content = """Some text with a [link](https://example.com/page) and
another [reference](https://arxiv.org/abs/1234.5678) and
a raw url https://docs.python.org/3/"""

    sources, url_map = extract_citations_from_content(content)

    assert "src-1" in sources or "src-2" in sources or "src-3" in sources
    assert "https://example.com/page" in url_map
    assert "https://arxiv.org/abs/1234.5678" in url_map
    assert "https://docs.python.org/3/" in url_map


def test_citation_replacement():
    """Citation tag replacement produces correct markdown."""
    from app.tools.citations import replace_citation_tags

    sources = {
        "src-1": {
            "short_id": "src-1",
            "title": "Example Page",
            "url": "https://example.com",
            "domain": "example.com",
        }
    }

    text = 'According to the paper<cite source="src-1" />, this is true.'
    result = replace_citation_tags(text, sources)

    assert "[Example Page](https://example.com)" in result
    assert "<cite" not in result


def test_merge_findings_extracts_citations():
    """merge_findings_node extracts citations from parallel findings."""
    from app.agent import merge_findings_node

    state: ResearchState = {
        "topic": "test",
        "plan_approved": True,
        "research_plan": "plan",
        "report_sections": None,
        "section_research_findings": None,
        "research_evaluation": None,
        "research_iteration": 0,
        "url_to_short_id": {},
        "sources": {},
        "final_cited_report": None,
        "final_report_with_citations": None,
        "messages": [],
        "iteration_count": 0,
        "max_iterations": 5,
        "user_feedback": None,
        "errors": [],
        "current_goal": "",
        "parallel_goals": [],
        "evaluation_scores": [],
        "total_tokens": 0,
        "cached_goal_count": 0,
        "depth": "standard",
        "parallel_findings": [
            "Finding 1 with [Example](https://example.com)",
            "Finding 2 with [ArXiv](https://arxiv.org/abs/1234)",
        ],
    }

    result = merge_findings_node(state)

    assert "section_research_findings" in result
    assert "sources" in result
    assert "url_to_short_id" in result

    sources = result["sources"]
    url_map = result["url_to_short_id"]

    assert len(sources) >= 2
    assert "https://example.com" in url_map
    assert "https://arxiv.org/abs/1234" in url_map
    # arxiv should be tier 1
    arxiv_src = sources.get(url_map["https://arxiv.org/abs/1234"])
    if arxiv_src:
        assert arxiv_src["tier"] == 1


def test_planner_skips_when_approved():
    """planner_node returns empty dict when plan is already approved."""
    from app.nodes.planner import planner_node

    state: ResearchState = {
        "topic": "test topic",
        "plan_approved": True,
        "research_plan": "Existing plan",
        "report_sections": None,
        "section_research_findings": None,
        "research_evaluation": None,
        "research_iteration": 0,
        "url_to_short_id": {},
        "sources": {},
        "final_cited_report": None,
        "final_report_with_citations": None,
        "messages": [],
        "iteration_count": 0,
        "max_iterations": 5,
        "user_feedback": None,
        "errors": [],
        "current_goal": "",
        "parallel_goals": [],
        "evaluation_scores": [],
        "total_tokens": 0,
        "cached_goal_count": 0,
        "depth": "standard",
        "parallel_findings": [],
    }

    result = planner_node(state)
    assert result == {}


def test_planner_generates_plan_when_not_approved():
    """planner_node generates plan when not approved."""
    from app.nodes.planner import planner_node
    import unittest.mock

    # Mock LLM to return a pre-canned plan (avoid real API call)
    mock_llm = unittest.mock.MagicMock()
    mock_response = unittest.mock.MagicMock()
    mock_response.content = (
        "[RESEARCH] Investigate LangGraph checkpointing\n"
        "[RESEARCH] Research state pruning techniques\n"
        "[DELIVERABLE] Synthesize findings into guide\n"
    )
    mock_llm.invoke.return_value = mock_response
    mock_llm.token_delta.return_value = {"total_tokens": 100}

    state: ResearchState = {
        "topic": "test topic",
        "plan_approved": False,
        "research_plan": None,
        "report_sections": None,
        "section_research_findings": None,
        "research_evaluation": None,
        "research_iteration": 0,
        "url_to_short_id": {},
        "sources": {},
        "final_cited_report": None,
        "final_report_with_citations": None,
        "messages": [],
        "iteration_count": 0,
        "max_iterations": 5,
        "user_feedback": None,
        "errors": [],
        "current_goal": "",
        "parallel_goals": [],
        "evaluation_scores": [],
        "total_tokens": 0,
        "cached_goal_count": 0,
        "depth": "standard",
        "parallel_findings": [],
    }

    with unittest.mock.patch("app.nodes.planner._get_llm", return_value=mock_llm):
        result = planner_node(state)
    assert "research_plan" in result
    assert "parallel_goals" in result
    assert "[DELIVERABLE]" in result["research_plan"]


def test_selects_retail_investor_template_for_ipo_question():
    """Planner heuristics classify retail-investor topics correctly."""
    from app.nodes.planner import select_report_template

    template = select_report_template("Should I invest in the SpaceX IPO as a retail investor?")

    assert template == "retail_investor_memo"


def test_generate_plan_only_returns_report_blueprint():
    """generate_plan_only returns a serialized report blueprint."""
    from app.nodes.planner import generate_plan_only
    import unittest.mock

    mock_llm = unittest.mock.MagicMock()
    mock_response = unittest.mock.MagicMock()
    mock_response.content = (
        "[RESEARCH] Analyze the company offering\n"
        "[RESEARCH] Compare valuation scenarios\n"
        "[DELIVERABLE] Produce investor recommendation\n"
    )
    mock_llm.invoke.return_value = mock_response
    mock_llm.token_delta.return_value = {"total_tokens": 100}

    with unittest.mock.patch("app.nodes.planner._get_llm", return_value=mock_llm):
        result = generate_plan_only("Should I invest in the SpaceX IPO as a retail investor?", enriched=False)

    blueprint = result.get("report_blueprint")
    assert isinstance(blueprint, dict)
    assert blueprint["template"] == "retail_investor_memo"
    assert blueprint["audience"] == "retail investor"
    assert blueprint["sections"]
    assert "## What Is Being Decided" in result["report_sections"]


def test_generate_blueprint_and_sections_prefers_template_structure_for_specialized_reports():
    """Specialized templates should enforce deterministic section headings."""
    from app.nodes.planner import generate_blueprint_and_sections

    blueprint, sections = generate_blueprint_and_sections(
        topic="Should I invest in the SpaceX IPO as a retail investor?",
        plan="[RESEARCH] Analyze the company offering\n[DELIVERABLE] Produce investor recommendation",
        sections_markdown="## Generic Intro\n## Generic Risks",
    )

    assert blueprint.template == "retail_investor_memo"
    assert "## What Is Being Decided" in sections
    assert "## Valuation Scenarios" in sections
    assert "## Generic Intro" not in sections


def test_planner_node_returns_report_blueprint():
    """planner_node populates report_blueprint for graph execution too."""
    from app.nodes.planner import planner_node
    import unittest.mock

    mock_llm = unittest.mock.MagicMock()
    mock_response = unittest.mock.MagicMock()
    mock_response.content = (
        "[RESEARCH] Analyze the current agent architecture\n"
        "[RESEARCH] Compare improvement options\n"
        "[DELIVERABLE] Produce implementation roadmap\n"
    )
    mock_llm.invoke.return_value = mock_response
    mock_llm.token_delta.return_value = {"total_tokens": 100}

    state: ResearchState = {
        "topic": "How should we improve our LangGraph agent architecture?",
        "plan_approved": False,
        "research_plan": None,
        "report_sections": None,
        "report_blueprint": None,
        "section_research_findings": None,
        "research_evaluation": None,
        "research_iteration": 0,
        "url_to_short_id": {},
        "sources": {},
        "final_cited_report": None,
        "final_report_with_citations": None,
        "messages": [],
        "iteration_count": 0,
        "max_iterations": 5,
        "user_feedback": None,
        "errors": [],
        "current_goal": "",
        "parallel_goals": [],
        "evaluation_scores": [],
        "total_tokens": 0,
        "cached_goal_count": 0,
        "depth": "standard",
        "parallel_findings": [],
    }

    with unittest.mock.patch("app.nodes.planner._get_llm", return_value=mock_llm):
        result = planner_node(state)

    blueprint = result.get("report_blueprint")
    assert isinstance(blueprint, dict)
    assert blueprint["template"] == "architecture_review"
    assert blueprint["sections"]


def test_merge_findings_reuses_existing_source_id_for_duplicate_url():
    """Merge step normalizes duplicate URLs to one global source ID."""
    from app.agent import merge_findings_node
    from app.models import Citation, ResearchFinding

    finding_one = ResearchFinding(
        goal_text="Goal 1",
        summary="Finding one",
        citations=[Citation(short_id="src-1", title="Example", url="https://example.com", tier=2)],
    )
    finding_two = ResearchFinding(
        goal_text="Goal 2",
        summary="Finding two",
        citations=[Citation(short_id="src-1", title="Example duplicate", url="https://example.com", tier=2)],
    )

    state: ResearchState = {
        "topic": "test",
        "plan_approved": True,
        "research_plan": "plan",
        "report_sections": None,
        "report_blueprint": None,
        "section_research_findings": None,
        "research_evaluation": None,
        "research_iteration": 0,
        "url_to_short_id": {},
        "sources": {},
        "final_cited_report": None,
        "final_report_with_citations": None,
        "messages": [],
        "iteration_count": 0,
        "max_iterations": 5,
        "user_feedback": None,
        "errors": [],
        "current_goal": "",
        "parallel_goals": [],
        "evaluation_scores": [],
        "total_tokens": 0,
        "cached_goal_count": 0,
        "depth": "standard",
        "parallel_findings": [finding_one, finding_two],
    }

    result = merge_findings_node(state)

    assert result["url_to_short_id"] == {"https://example.com": "src-1"}
    assert list(result["sources"]) == ["src-1"]


def test_build_evidence_appendix_from_state():
    """Composer builds a deterministic evidence appendix from state data."""
    from app.nodes.composer import build_evidence_appendix

    appendix = build_evidence_appendix(
        sources={
            "src-1": {
                "short_id": "src-1",
                "title": "SEC Filing",
                "url": "https://sec.gov/example",
                "domain": "sec.gov",
                "tier": 1,
                "source_type": "official",
                "authority_reason": "Primary filing",
                "used_for_claims": ["claim-1"],
            }
        },
        evidence_claims=[
            {
                "claim_id": "claim-1",
                "text": "Revenue grew 20% year over year.",
                "confidence": 4,
                "support_source_ids": ["src-1"],
                "evidence_strength": "high",
            }
        ],
        evidence_gaps=[
            {
                "gap_id": "gap-1",
                "description": "No audited quarterly cash flow statement found",
                "why_it_matters": "Liquidity risk is unclear",
                "impact_on_conclusion": "medium",
            }
        ],
    )

    assert "## Evidence Appendix" in appendix
    assert "SEC Filing" in appendix
    assert "Revenue grew 20% year over year." in appendix
    assert "No audited quarterly cash flow statement found" in appendix


def test_build_evidence_appendix_omits_empty_appendix():
    """Composer should not append empty evidence tables."""
    from app.nodes.composer import build_evidence_appendix

    appendix = build_evidence_appendix(sources={}, evidence_claims=[], evidence_gaps=[])

    assert appendix == ""


def test_template_block_config_uses_retail_investor_sections():
    """Composer exposes retail-investor report blocks deterministically."""
    from app.nodes.composer import get_template_block_config

    blocks = get_template_block_config(
        {
            "template": "retail_investor_memo",
            "required_sections": [],
        }
    )

    assert "what_is_being_decided" in blocks
    assert "scenario_table" in blocks
    assert "decision_checklist" in blocks


def test_report_critic_fails_missing_required_section():
    """Report critic should fail when blueprint-required sections are missing."""
    from app.nodes.report_critic import report_critic_node

    state: ResearchState = {
        "topic": "Should I invest in SpaceX?",
        "plan_approved": True,
        "research_plan": "plan",
        "report_sections": "## Executive Summary\n## Recommendation",
        "report_blueprint": {
            "template": "retail_investor_memo",
            "sections": [
                {"title": "Executive Summary", "purpose": "summary"},
                {"title": "What Is Being Decided", "purpose": "decision framing"},
                {"title": "Recommendation", "purpose": "decision"},
            ],
            "required_decision_artifacts": ["decision_checklist"],
        },
        "section_research_findings": "findings",
        "research_evaluation": None,
        "research_iteration": 0,
        "url_to_short_id": {},
        "sources": {},
        "evidence_claims": [],
        "evidence_gaps": [],
        "final_cited_report": "# Report\n\n## Executive Summary\nAnswer.\n\n## Recommendation\nBuy.",
        "final_report_with_citations": "# Report\n\n## Executive Summary\nAnswer.\n\n## Recommendation\nBuy.",
        "report_critic_result": None,
        "report_critic_passed": False,
        "messages": [],
        "iteration_count": 0,
        "max_iterations": 5,
        "user_feedback": None,
        "errors": [],
        "current_goal": "",
        "parallel_goals": [],
        "evaluation_scores": [],
        "total_tokens": 0,
        "cached_goal_count": 0,
        "depth": "standard",
        "parallel_findings": [],
    }

    result = report_critic_node(state)

    assert result["report_critic_passed"] is False
    assert "What Is Being Decided" in "\n".join(result["report_critic_result"]["hard_failures"])


def test_report_critic_passes_complete_cited_report():
    """Report critic should pass a complete cited report and append QA summary."""
    from app.nodes.report_critic import report_critic_node

    report = """# Report

## Executive Summary
SpaceX remains private and any retail exposure would likely be indirect. [src-1]

## What Is Being Decided
Whether a retail investor should seek pre-IPO exposure. [src-1]

## Recommendation
Wait for audited public disclosures before taking indirect exposure.

## Evidence Appendix
| Source | Tier |
|---|---:|
| src-1 | 1 |
"""
    state: ResearchState = {
        "topic": "Should I invest in SpaceX?",
        "plan_approved": True,
        "research_plan": "plan",
        "report_sections": "## Executive Summary\n## What Is Being Decided\n## Recommendation",
        "report_blueprint": {
            "template": "retail_investor_memo",
            "sections": [
                {"title": "Executive Summary", "purpose": "summary"},
                {"title": "What Is Being Decided", "purpose": "decision framing"},
                {"title": "Recommendation", "purpose": "decision"},
            ],
            "required_decision_artifacts": [],
        },
        "section_research_findings": "findings",
        "research_evaluation": None,
        "research_iteration": 0,
        "url_to_short_id": {"https://example.com": "src-1"},
        "sources": {"src-1": {"short_id": "src-1", "title": "Example", "url": "https://example.com", "tier": 1}},
        "evidence_claims": [],
        "evidence_gaps": [],
        "final_cited_report": report,
        "final_report_with_citations": report,
        "report_critic_result": None,
        "report_critic_passed": False,
        "messages": [],
        "iteration_count": 0,
        "max_iterations": 5,
        "user_feedback": None,
        "errors": [],
        "current_goal": "",
        "parallel_goals": [],
        "evaluation_scores": [],
        "total_tokens": 0,
        "cached_goal_count": 0,
        "depth": "standard",
        "parallel_findings": [],
    }

    result = report_critic_node(state)

    assert result["report_critic_passed"] is True
    assert result["report_critic_result"]["hard_failures"] == []
    assert "## Final QA" in result["final_report_with_citations"]


def test_rule_based_evaluation_clear_pass():
    """Rule-based pre-check returns PASS for substantial, cited, structured findings."""
    from app.nodes.evaluator import _rule_based_evaluation
    from app.state import Feedback
    import textwrap

    findings = textwrap.dedent("""
    ## Section 1
    Research shows that AI models improved by 15% in 2024.
    Source: https://example.com/paper1

    ## Section 2
    Another study found 23% gains: https://example.com/paper2
    And https://example.com/paper3 confirms this trend.
    Additional context with more text to ensure we exceed the 1000 char threshold.
    This provides substantial content about the research findings.
    Multiple studies confirm the results across different domains.
    The evidence is consistent and well-documented in the literature.
    """)
    result = _rule_based_evaluation(findings, "AI progress")
    assert result is not None
    assert isinstance(result, Feedback)
    assert result.grade == "pass"
    assert "4/5" in result.comment


def test_rule_based_evaluation_clear_fail():
    """Rule-based pre-check returns FAIL for findings with no citations."""
    from app.nodes.evaluator import _rule_based_evaluation
    from app.state import Feedback

    findings = "Some vague claims about AI without any sources or numbers."
    result = _rule_based_evaluation(findings, "AI progress")
    assert result is not None
    assert isinstance(result, Feedback)
    assert result.grade == "fail"
    assert result.follow_up_queries is not None
    assert len(result.follow_up_queries) > 0


def test_rule_based_evaluation_ambiguous():
    """Rule-based pre-check returns None for ambiguous findings (fall through to LLM)."""
    from app.nodes.evaluator import _rule_based_evaluation
    import textwrap

    # Has URLs and some structure but not clearly pass or fail
    # (not enough URLs for clear pass, not empty enough for clear fail)
    findings = textwrap.dedent("""
    Some preliminary research on the topic with initial observations.
    https://example.com/source1 provides some background.
    No clear quantitative data yet but some qualitative insights exist.
    This needs more investigation to draw firm conclusions.
    """)
    result = _rule_based_evaluation(findings, "topic")
    assert result is None  # ambiguous, should fall through to LLM


def test_evaluator_disabled_auto_pass():
    """When ENABLE_EVALUATOR=false, evaluator auto-passes without LLM call."""
    from app.nodes.evaluator import research_evaluator_node
    import unittest.mock

    state: ResearchState = {
        "topic": "test",
        "plan_approved": True,
        "research_plan": "plan",
        "report_sections": None,
        "section_research_findings": "some findings with https://example.com/data",
        "research_evaluation": None,
        "research_iteration": 0,
        "url_to_short_id": {},
        "sources": {},
        "final_cited_report": None,
        "final_report_with_citations": None,
        "messages": [],
        "iteration_count": 0,
        "max_iterations": 5,
        "user_feedback": None,
        "errors": [],
        "current_goal": "",
        "parallel_goals": [],
        "evaluation_scores": [],
        "total_tokens": 0,
        "cached_goal_count": 0,
        "depth": "standard",
        "parallel_findings": [],
    }

    with unittest.mock.patch("app.nodes.evaluator.config") as mock_config:
        mock_config.enable_evaluator = False
        result = research_evaluator_node(state)

    assert result["research_evaluation"].grade == "pass"


def test_config_validation_missing_api_key():
    """Config validation catches missing WORKER_API_KEY."""
    from app.config import ResearchConfig
    cfg = ResearchConfig()
    cfg.worker_api_key = ""
    issues = cfg.validate()
    assert any("WORKER_API_KEY" in i for i in issues)


def test_config_validation_missing_api_base():
    """Config validation catches missing WORKER_API_BASE."""
    from app.config import ResearchConfig
    cfg = ResearchConfig()
    cfg.worker_api_base = ""
    issues = cfg.validate()
    assert any("WORKER_API_BASE" in i for i in issues)


def test_config_validation_valid_config():
    """Config validation returns empty for valid config."""
    from app.config import ResearchConfig
    cfg = ResearchConfig()
    cfg.worker_api_key = "sk-placeholder"
    cfg.worker_api_base = "https://api.deepseek.com"
    cfg.critic_model = "different-model"
    issues = cfg.validate()
    assert len(issues) == 0


def test_config_validation_critic_same_as_worker():
    """Config validation warns when critic == worker."""
    from app.config import ResearchConfig
    cfg = ResearchConfig()
    cfg.worker_api_key = "sk-placeholder"
    cfg.worker_api_base = "https://api.deepseek.com"
    cfg.worker_model = "deepseek-v4-flash"
    cfg.critic_model = "deepseek-v4-flash"
    issues = cfg.validate()
    assert any("same as WORKER_MODEL" in i or "Same-model" in i for i in issues)


# ── Type-safe accessor tests ──


def test_findings_from_state_empty():
    """findings_from_state returns empty list for empty state."""
    from app.models import findings_from_state
    result = findings_from_state({})
    assert result == []


def test_findings_from_state_with_findings():
    """findings_from_state parses section_research_findings into typed models."""
    from app.models import findings_from_state, ResearchFinding
    state = {
        "section_research_findings": (
            "### Research: Test goal\n\nSome findings with [Source](https://example.com/a).\n\n"
            "---\n\n"
            "### Research: Goal two\n\nMore data at [Link](https://example.com/b).\n"
        ),
        "sources": {
            "src-1": {"url": "https://example.com/a", "title": "Source A", "tier": 2},
        },
    }
    result = findings_from_state(state)
    assert len(result) >= 1
    assert isinstance(result[0], ResearchFinding)
    assert any("Test goal" in r.goal_text for r in result)


def test_findings_to_state_serializes():
    """findings_to_state produces state-compatible dict."""
    from app.models import findings_to_state, ResearchFinding, Citation
    findings = [
        ResearchFinding(
            goal_text="Test",
            summary="Content with [Link](https://example.com/x)",
            citations=[Citation(short_id="src-1", url="https://example.com/x", title="X", tier=2)],
        ),
    ]
    result = findings_to_state(findings)
    assert "section_research_findings" in result
    assert "sources" in result
    assert "url_to_short_id" in result
    assert len(result["sources"]) == 1


def test_get_typed_sources():
    """get_typed_sources converts state sources dict to Citation objects."""
    from app.models import get_typed_sources, Citation
    state = {
        "sources": {
            "src-1": {"url": "https://example.com", "title": "Test", "tier": 1},
        },
    }
    result = get_typed_sources(state)
    assert "src-1" in result
    assert isinstance(result["src-1"], Citation)
    assert result["src-1"].tier == 1


# ── Serialize sources tests ──


def test_serialize_sources_strips_heavy_fields():
    """_serialize_sources only passes essential fields to LLM prompt."""
    from app.nodes.composer import _serialize_sources
    sources = {
        "src-1": {
            "short_id": "src-1",
            "title": "Test Source",
            "url": "https://example.com",
            "tier": 2,
            "authority_reason": "Well-known engineering blog with good reputation",
            "supported_claims": ["Claim A", "Claim B", "Claim C"],
        },
    }
    result = _serialize_sources(sources)
    import json
    parsed = json.loads(result)
    src = parsed["src-1"]
    assert "short_id" in src
    assert "url" in src
    assert "title" in src
    assert "tier" in src
    assert "authority_reason" not in src, "Should drop authority_reason"
    assert "supported_claims" not in src, "Should drop supported_claims"


# ── Browser extraction test ──


def test_browser_extraction_graceful_degradation():
    """_fetch_via_browser returns empty string when Playwright not installed."""
    import unittest.mock
    with unittest.mock.patch("app.tools.search.logger"):
        from app.tools.search import _fetch_via_browser
        # Playwright not installed in test venv — should return ""
        result = _fetch_via_browser("https://example.com", max_chars=500)
        assert isinstance(result, str)
        assert result == ""  # graceful degradation


def test_search_wrapper_passes_language_to_backend():
    """Search wrapper preserves requested language for backend selection."""
    from app.tools.search import _SearchWrapper

    calls = {}

    def fake_impl(query: str, max_results: int = 5, language: str | None = None):
        calls["query"] = query
        calls["max_results"] = max_results
        calls["language"] = language
        return []

    wrapper = _SearchWrapper(fake_impl)
    wrapper.invoke({"query": "nacionalidad española", "max_results": 3, "language": "Spanish"})

    assert calls == {
        "query": "nacionalidad española",
        "max_results": 3,
        "language": "Spanish",
    }


def test_duckduckgo_search_maps_language_to_region(monkeypatch):
    """DDGS fallback maps language hints to region-specific search locales."""
    import app.tools.search as search

    calls = {}

    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def text(self, query, **kwargs):
            calls["query"] = query
            calls.update(kwargs)
            return [{"title": "A", "href": "https://example.com", "body": "snippet"}]

    monkeypatch.setattr(search, "DDGS", FakeDDGS)
    results = search._duckduckgo_search("nacionalidad española", max_results=2, language="Spanish")

    assert calls["region"] == "es-es"
    assert results[0]["url"] == "https://example.com"


def test_tavily_search_routes_non_english_queries_to_searxng(monkeypatch):
    """Non-English Tavily requests route through SearXNG when available."""
    import app.tools.search as search

    monkeypatch.setattr(search, "_searxng_is_reachable", lambda base_url=None: True)
    monkeypatch.setattr(
        search,
        "_searxng_search",
        lambda query, max_results=5, base_url=None, language=None: [{
            "title": "SearXNG",
            "url": "https://example.com/searxng",
            "snippet": language or "",
        }],
    )

    results = search._tavily_search("nacionalidad española", max_results=1, language="Spanish")

    assert results == [{
        "title": "SearXNG",
        "url": "https://example.com/searxng",
        "snippet": "Spanish",
    }]


def test_normalize_language_hint_supports_native_names_with_diacritics():
    """Language hints like 'español' normalize to the correct search code."""
    from app.tools.search import _normalize_language_hint

    assert _normalize_language_hint("español") == "es"
    assert _normalize_language_hint("français") == "fr"
    assert _normalize_language_hint("Português") == "pt"
    assert _normalize_language_hint("Català") == "ca"


def test_infer_language_from_query_prefers_german_for_umlaut_only_queries():
    """German umlaut-only queries should not be misclassified as Spanish."""
    from app.tools.search import _infer_language_from_query

    assert _infer_language_from_query("Urteil für München") == "de"


def test_research_single_goal_passes_language_hint_to_search_backend():
    """Research goals annotated with a language hint search in that language."""
    from app.nodes.researcher import _research_single_goal

    class FakeLLM:
        def __init__(self):
            self.calls = 0

        def invoke(self, messages):
            self.calls += 1
            if self.calls == 1:
                return type("Resp", (), {"content": '["consulta oficial"]'})()
            return type("Resp", (), {
                "content": "Hallazgo con [Fuente](https://example.com/fuente). [CONFIDENCE:4]"
            })()

    class FakeSearchTool:
        def __init__(self):
            self.languages = []

        def invoke(self, params):
            self.languages.append(params.get("language"))
            return [{"title": "Fuente", "url": "https://example.com/fuente", "snippet": "contenido"}]

    search_tool = FakeSearchTool()
    finding = _research_single_goal(
        "Analiza la validez del certificado CCSE (search in Spanish; sources: boe.es)",
        search_tool,
        FakeLLM(),
    )

    assert finding.goal_text.startswith("Analiza la validez")
    assert finding.search_queries == ["consulta oficial"]
    assert search_tool.languages == ["Spanish"]
    assert finding.citations[0].url == "https://example.com/fuente"


def test_cli_help_does_not_require_config(monkeypatch, capsys):
    """CLI --help should print usage without requiring API env vars."""
    import app.cli as cli

    monkeypatch.setattr("sys.argv", ["deep-research", "--help"])

    try:
        cli.main()
    except SystemExit as exc:
        assert exc.code == 0

    captured = capsys.readouterr()
    assert "Deep Research Agent" in captured.out
    assert "WORKER_API_KEY" not in captured.err
