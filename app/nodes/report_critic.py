from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import config
from app.state import ResearchState


def _get_llm() -> Any:
    from app.tokens import get_llm

    return get_llm(
        model=config.critic_model,
        temperature=0.1,
        api_key=config.critic_api_key or config.worker_api_key or None,
        base_url=config.critic_api_base or config.worker_api_base or None,
        node_name="report_critic",
    )


def _extract_heading_titles(report: str) -> set[str]:
    return {
        match.group(1).strip().lower()
        for match in re.finditer(r"^##\s+(.+)$", report, flags=re.MULTILINE)
    }


def _extract_required_section_titles(report_blueprint: dict | None) -> list[str]:
    if not report_blueprint:
        return []
    sections = report_blueprint.get("sections", [])
    titles: list[str] = []
    for section in sections:
        title = (section or {}).get("title")
        if title:
            titles.append(str(title).strip())
    return titles


def _artifact_label_map() -> dict[str, str]:
    return {
        "decision_checklist": "Decision Checklist",
        "scenario_table": "Scenario Table",
        "base_case": "Base Case",
        "bull_case": "Bull Case",
        "bear_case": "Bear Case",
        "evidence_appendix": "Evidence Appendix",
    }


def _parse_semantic_qa(text: str) -> dict | None:
    raw = text.strip()
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if json_match:
        raw = json_match.group(1).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start : end + 1]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _run_semantic_qa(report: str, report_blueprint: dict, sufficiency: dict | None) -> tuple[list[str], list[str], dict]:
    try:
        llm = _get_llm()
        response = llm.invoke([
            SystemMessage(content=(
                "You are a final report critic. Return JSON only with keys "
                "warnings (list of strings) and hard_failures (list of strings). "
                "Only use hard_failures for severe issues like hidden contradictions, "
                "uncited major claims, or recommendation strength that overstates the evidence."
            )),
            HumanMessage(content=(
                f"REPORT BLUEPRINT:\n{json.dumps(report_blueprint or {}, indent=2)}\n\n"
                f"SUFFICIENCY ASSESSMENT:\n{json.dumps(sufficiency or {}, indent=2)}\n\n"
                f"REPORT:\n{report}"
            )),
        ])
        parsed = _parse_semantic_qa(getattr(response, "content", ""))
        if parsed is None:
            return ["semantic QA returned unparsable output"], [], llm.token_delta()
        warnings = [str(item) for item in parsed.get("warnings", []) if str(item).strip()]
        hard_failures = [str(item) for item in parsed.get("hard_failures", []) if str(item).strip()]
        return warnings, hard_failures, llm.token_delta()
    except Exception as exc:
        return [f"semantic QA unavailable: {exc.__class__.__name__}"], [], {}


def _append_final_qa(report: str, critic_result: dict, sufficiency: dict | None) -> str:
    if "## Final QA" in report:
        return report

    sufficiency = sufficiency or {}
    status = "PASS" if not critic_result.get("hard_failures") else "FAIL"
    warnings = critic_result.get("warnings") or []
    missing_sections = critic_result.get("missing_sections") or []
    missing_artifacts = critic_result.get("missing_artifacts") or []
    blocking_gaps = sufficiency.get("blocking_gaps") or []
    recommendation_strength = sufficiency.get("recommendation_strength")

    report_body = report.rstrip()
    if blocking_gaps and recommendation_strength:
        lines = ["", "## Recommendation Constraints", ""]
        if recommendation_strength == "no_recommendation":
            lines.append("Do not make a decisive recommendation yet. Required evidence is still missing.")
        elif recommendation_strength == "low":
            lines.append("Any recommendation here should be treated as tentative because required evidence is still missing.")
        lines.append(f"Current recommendation strength: {recommendation_strength}")
        lines.append(f"Open gaps: {'; '.join(blocking_gaps)}")
        report_body += "\n" + "\n".join(lines) + "\n"

    lines = ["", "## Final QA", "", f"- Status: {status}"]
    if recommendation_strength:
        lines.append(f"- Recommendation strength: {recommendation_strength}")
    if missing_sections:
        lines.append(f"- Missing sections: {', '.join(missing_sections)}")
    if missing_artifacts:
        lines.append(f"- Missing artifacts: {', '.join(missing_artifacts)}")
    if blocking_gaps:
        lines.append(f"- Blocking gaps: {'; '.join(blocking_gaps)}")
    if warnings:
        lines.append(f"- Warnings: {'; '.join(warnings)}")
    return report_body + "\n" + "\n".join(lines) + "\n"


def report_critic_node(state: ResearchState) -> dict:
    report = state.get("final_report_with_citations") or state.get("final_cited_report") or ""
    if not config.enable_report_critic:
        return {
            "report_critic_result": {"warnings": ["report critic disabled by configuration"], "hard_failures": []},
            "report_critic_passed": True,
            "final_report_with_citations": report,
        }

    report_blueprint = state.get("report_blueprint") or {}
    sufficiency = state.get("sufficiency_assessment") or {}
    sources = state.get("sources") or {}
    depth = state.get("depth", "standard")

    required_sections = _extract_required_section_titles(report_blueprint)
    present_headings = _extract_heading_titles(report)
    missing_sections = [title for title in required_sections if title.lower() not in present_headings]

    required_artifacts = list(report_blueprint.get("required_decision_artifacts") or [])
    artifact_labels = _artifact_label_map()
    missing_artifacts = []
    lowered_report = report.lower()
    for artifact in required_artifacts:
        artifact_label = artifact_labels.get(str(artifact), str(artifact).replace("_", " ").title())
        if artifact_label.lower() not in lowered_report:
            missing_artifacts.append(artifact_label)

    warnings: list[str] = []
    hard_failures: list[str] = []
    if not report.strip():
        hard_failures.append("No final report was generated")
    if missing_sections:
        hard_failures.extend([f"Missing required section: {title}" for title in missing_sections])
    if missing_artifacts:
        hard_failures.extend([f"Missing required artifact: {label}" for label in missing_artifacts])
    has_inline_citations = bool(
        re.search(r"\[src-\d+\]", report)
        or re.search(r"<cite\s+source=\"[^\"]+\"\s*/?>", report)
        or re.search(r"\[[^\]]+\]\(https?://[^\)]+\)", report)
    )
    if sources and not has_inline_citations and depth != "brief":
        hard_failures.append("Report is missing inline citations")
    if sources and "## Evidence Appendix" not in report and depth != "brief":
        warnings.append("report is missing Evidence Appendix")

    semantic_warnings, semantic_failures, token_delta = _run_semantic_qa(report, report_blueprint, sufficiency)
    warnings.extend(semantic_warnings)
    hard_failures.extend(semantic_failures)

    critic_result = {
        "missing_sections": missing_sections,
        "missing_artifacts": missing_artifacts,
        "hard_failures": list(dict.fromkeys(hard_failures)),
        "warnings": list(dict.fromkeys(warnings)),
    }
    passed = not critic_result["hard_failures"]

    return {
        "report_critic_result": critic_result,
        "report_critic_passed": passed,
        "final_report_with_citations": _append_final_qa(report, critic_result, sufficiency),
        **token_delta,
    }
