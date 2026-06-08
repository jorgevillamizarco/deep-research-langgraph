from __future__ import annotations

import re

from app.state import ResearchState


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


def _append_final_qa(report: str, critic_result: dict) -> str:
    if "## Final QA" in report:
        return report

    status = "PASS" if not critic_result.get("hard_failures") else "FAIL"
    warnings = critic_result.get("warnings") or []
    missing_sections = critic_result.get("missing_sections") or []
    missing_artifacts = critic_result.get("missing_artifacts") or []

    lines = ["", "## Final QA", "", f"- Status: {status}"]
    if missing_sections:
        lines.append(f"- Missing sections: {', '.join(missing_sections)}")
    if missing_artifacts:
        lines.append(f"- Missing artifacts: {', '.join(missing_artifacts)}")
    if warnings:
        lines.append(f"- Warnings: {'; '.join(warnings)}")
    return report.rstrip() + "\n" + "\n".join(lines) + "\n"


def report_critic_node(state: ResearchState) -> dict:
    report = state.get("final_report_with_citations") or state.get("final_cited_report") or ""
    report_blueprint = state.get("report_blueprint") or {}
    sources = state.get("sources") or {}

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
    if sources and not re.search(r"\[src-\d+\]", report):
        warnings.append("report is missing inline [src-N] citations")
    if sources and "## Evidence Appendix" not in report:
        warnings.append("report is missing Evidence Appendix")

    hard_failures: list[str] = []
    if missing_sections:
        hard_failures.extend([f"Missing required section: {title}" for title in missing_sections])
    if missing_artifacts:
        hard_failures.extend([f"Missing required artifact: {label}" for label in missing_artifacts])

    critic_result = {
        "missing_sections": missing_sections,
        "missing_artifacts": missing_artifacts,
        "hard_failures": hard_failures,
        "warnings": warnings,
    }
    passed = not hard_failures

    return {
        "report_critic_result": critic_result,
        "report_critic_passed": passed,
        "final_report_with_citations": _append_final_qa(report, critic_result),
    }
