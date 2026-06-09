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


def _heading_present(title: str, headings: set[str]) -> bool:
    """Check if required heading title appears as substring of any extracted heading."""
    lowered = title.lower()
    return any(lowered in h for h in headings)


def _section_content_present(title: str, report_lowered: str) -> bool:
    """Check if report body contains content about the section topic.

    Uses keyword presence rather than heading strings — LLMs vary
    heading wording, so 'State Management Strategies' may appear as
    '## 2. State Management' in the actual report.
    """
    stop = {"the", "and", "for", "with", "that", "this", "from", "are", "was",
            "were", "have", "has", "had", "been", "can", "will", "may", "could",
            "would", "should", "also", "more", "some", "than", "into", "over",
            "only", "other", "such", "both", "just", "its", "use", "using", 
            "based", "versus", "approaches", "patterns", "framework", "analysis",
            "comparative", "deployment", "strategies", "execution", "backends"}
    words = [w for w in re.findall(r"[a-z]{3,}", title.lower()) if w not in stop]
    if len(words) < 2:
        return title.lower() in report_lowered
    matches = sum(1 for w in words if w in report_lowered)
    return matches >= min(2, len(words))


def _artifact_label_map() -> dict[str, str]:
    return {
        "decision_checklist": "Decision Checklist",
        "scenario_table": "Scenario Table",
        "base_case": "Base Case",
        "bull_case": "Bull Case",
        "bear_case": "Bear Case",
        "evidence_appendix": "Evidence Appendix",
    }


def _detect_duplicate_sources(report: str) -> list[str]:
    """Scan Source Register for URLs appearing under multiple src-IDs."""
    url_to_ids: dict[str, list[str]] = {}
    for line in report.splitlines():
        match = re.search(r"src-(\d+):\s*\[.*?\]\((https?://[^\)]+)\)", line)
        if match:
            src_id = match.group(1)
            url = match.group(2).strip().rstrip("/")
            url_to_ids.setdefault(url, []).append(src_id)
    warnings = []
    for url, ids in url_to_ids.items():
        if len(ids) > 1:
            warnings.append(f"Duplicate source: URL appears as src-{ids[0]} and src-{', '.join(ids[1:])} ({url})")
    if len(warnings) <= 3:
        return warnings
    return [f"{len(warnings)} duplicate source entries found in Source Register (same URL under different src-IDs)"]


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
                "uncited major claims, or recommendation strength that overstates the evidence. "
                "Use warnings for issues the report itself acknowledges or qualifies. "
                "If the report explicitly discloses a limitation (e.g., 'scores are derived "
                "from inference', 'confidence is moderate', 'based on logical inference "
                "rather than benchmarks'), flag it as a warning, not a hard failure.\n\n"
                "Check for these specific issues:\n"
                "- Unsupported quantitative claims: any percentages, thresholds, or "
                "specific numbers (e.g., '20%', '90%', '3 months') that lack a cited "
                "source directly supporting that exact number.\n"
                "- Mechanism misattribution: claims that attribute an effect to the "
                "wrong mechanism (e.g., claiming 'mocking reduces hallucination by 90%' "
                "when the source says 'output validation' does).\n"
                "- Unsourced production readiness notes: directives like 'keep at least "
                "X% optional' or 'run tests every N minutes' that lack citations.\n"
                "- Empty or placeholder sections: tables with headers but no data rows."
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
    hard_failures = critic_result.get("hard_failures") or []
    missing_sections = critic_result.get("missing_sections") or []
    missing_artifacts = critic_result.get("missing_artifacts") or []
    blocking_gaps = sufficiency.get("blocking_gaps") or []
    contradictions = sufficiency.get("contradictions") or []
    recommendation_strength = sufficiency.get("recommendation_strength")
    source_diversity = sufficiency.get("source_diversity")

    report_body = report.rstrip()
    if (blocking_gaps or contradictions) and recommendation_strength:
        lines = ["", "## Recommendation Constraints", ""]
        if recommendation_strength == "no_recommendation":
            lines.append("Do not make a decisive recommendation yet. Required evidence is still missing.")
        elif recommendation_strength == "low":
            lines.append("Any recommendation here should be treated as tentative because required evidence is still missing.")
        lines.append(f"Current recommendation strength: {recommendation_strength}")
        if blocking_gaps:
            lines.append(f"Open gaps: {'; '.join(blocking_gaps)}")
        if contradictions:
            lines.append(f"Unresolved contradictions: {'; '.join(contradictions)}")
        report_body += "\n" + "\n".join(lines) + "\n"

    lines = ["", "## Final QA", "", f"- Status: {status}"]
    if recommendation_strength:
        lines.append(f"- Recommendation strength: {recommendation_strength}")
    if source_diversity:
        lines.append(f"- Source diversity: {source_diversity}")
    if missing_sections:
        lines.append(f"- Missing sections: {', '.join(missing_sections)}")
    if missing_artifacts:
        lines.append(f"- Missing artifacts: {', '.join(missing_artifacts)}")
    if blocking_gaps:
        lines.append(f"- Blocking gaps: {'; '.join(blocking_gaps)}")
    if contradictions:
        lines.append(f"- Contradictions: {'; '.join(contradictions)}")
    if warnings:
        lines.append(f"- Warnings: {'; '.join(warnings)}")
    if hard_failures:
        lines.append(f"- Failures: {'; '.join(hard_failures)}")
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
    lowered_report = report.lower()
    missing_sections = [
        title for title in required_sections
        if not _section_content_present(title, lowered_report)
    ]

    required_artifacts = list(report_blueprint.get("required_decision_artifacts") or [])
    artifact_labels = _artifact_label_map()
    missing_artifacts = []
    for artifact in required_artifacts:
        artifact_label = artifact_labels.get(str(artifact), str(artifact).replace("_", " ").title())
        if artifact_label.lower() in lowered_report:
            continue
        short_words = artifact_label.lower().split()
        short_label = " ".join(short_words[:1]) if len(short_words) > 1 else artifact_label.lower()
        if len(short_label) >= 4 and short_label in lowered_report:
            continue
        missing_artifacts.append(artifact_label)

    warnings: list[str] = []
    hard_failures: list[str] = []
    if config.critic_model and config.worker_model and config.critic_model == config.worker_model:
        warnings.append("Critic model equals worker model — QA quality may be inflated. Consider setting CRITIC_MODEL to a stronger model.")
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
    if sources:
        dup_warnings = _detect_duplicate_sources(report)
        warnings.extend(dup_warnings)

    # Contradiction detection: extract claims from report, check for opposing ones
    try:
        from app.nodes.composer import _extract_claims_from_report
        from app.nodes.evaluator import _detect_contradictions
        extracted_claims = _extract_claims_from_report(report, sources)
        contradictions = _detect_contradictions(extracted_claims)
        if contradictions:
            hard_failures.extend([f"Contradiction: {c}" for c in contradictions])
    except Exception:
        pass  # contradiction detection is best-effort

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
