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
