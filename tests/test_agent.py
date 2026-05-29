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

    # This will call the LLM — we can't easily mock without more setup.
    # Just verify it doesn't crash and returns expected keys.
    # Skip in CI by checking for API key.
    import os
    if not os.getenv("WORKER_API_KEY"):
        return

    result = planner_node(state)
    assert "research_plan" in result
    assert "parallel_goals" in result
    assert "[DELIVERABLE]" in result["research_plan"]


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
