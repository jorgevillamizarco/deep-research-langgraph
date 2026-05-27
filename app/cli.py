"""CLI entry point for the deep research agent.

Usage:
    python -m app.cli "your research topic"
    python -m app.cli --auto "your topic"  (auto-approve plan, skip review)

The agent presents the research plan for your review before executing any
searches. You can approve it, provide feedback to refine it, or abort.
"""

from __future__ import annotations

import argparse
import datetime
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from langgraph.types import Command

from app.agent import build_research_graph
from app.config import config

logger = logging.getLogger(__name__)


def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _print_banner(title: str, rule: str = "=") -> None:
    """Print a section banner."""
    print(f"\n{rule * 60}")
    print(f"  {title}")
    print(f"{rule * 60}")


def _display_plan(plan: str, sections: str) -> None:
    """Display the research plan in a clean, readable format."""
    _print_banner("RESEARCH PLAN")
    print()
    for line in plan.split("\n"):
        print(f"  {line}")
    print()
    _print_banner("REPORT STRUCTURE")
    print()
    for line in sections.split("\n"):
        print(f"  {line}")
    print()


def _convert_to_pdf(md_path: Path) -> Path | None:
    """Convert a markdown file to PDF using pandoc + weasyprint.

    Args:
        md_path: Path to the markdown file.

    Returns:
        Path to the generated PDF, or None if conversion failed.
    """
    pdf_path = md_path.with_suffix(".pdf")

    # Try pandoc + weasyprint first (fastest, best CSS support)
    try:
        result = subprocess.run(
            [
                "pandoc", str(md_path),
                "-o", str(pdf_path),
                "--pdf-engine=weasyprint",
                "--metadata", "title=Deep Research Report",
                "--from", "markdown+pipe_tables+autolink_bare_uris",
                "-V", "margin-top=20mm", "-V", "margin-bottom=20mm",
                "-V", "margin-left=20mm", "-V", "margin-right=20mm",
            ],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0 and pdf_path.exists():
            return pdf_path
        logger.warning("Pandoc PDF conversion failed: %s", result.stderr[:200])
    except FileNotFoundError:
        logger.warning("Pandoc not found — skipping PDF generation")
    except Exception as e:
        logger.warning("Pandoc PDF conversion error: %s", e)

    # Fallback: weasyprint directly from markdown
    try:
        import markdown
        from weasyprint import HTML
        md_text = md_path.read_text()
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>body{{font-family:system-ui,sans-serif;max-width:800px;margin:auto;padding:20px;line-height:1.6;color:#1a1a1a}}
h1{{border-bottom:2px solid #333;padding-bottom:8px}}h2{{border-bottom:1px solid #ccc;padding-bottom:4px}}
a{{color:#0366d6}}code{{background:#f5f5f5;padding:2px 6px;border-radius:3px}}
pre{{background:#f5f5f5;padding:12px;border-radius:6px;overflow-x:auto}}
blockquote{{border-left:4px solid #ccc;margin-left:0;padding-left:16px;color:#666}}
table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ddd;padding:8px;text-align:left}}
th{{background:#f5f5f5}}</style></head><body>
{markdown.markdown(md_text, extensions=["tables","fenced_code","codehilite"])}
</body></html>"""
        HTML(string=html).write_pdf(str(pdf_path))
        if pdf_path.exists():
            return pdf_path
    except ImportError:
        logger.warning("markdown/weasyprint not available — skipping PDF fallback")
    except Exception as e:
        logger.warning("Weasyprint fallback failed: %s", e)

    return None


def run_research(topic: str, auto_approve: bool = False) -> str:
    """Execute full deep research workflow from the command line.

    Flow:
      1. Stream the graph to generate the plan → hits an interrupt for review
      2. Display plan, ask for user approval/feedback
      3. Resume with ``graph.invoke(Command(resume=...))`` — runs the rest
         of the pipeline (research → evaluation → composer)
      4. Save and return the final report (markdown + PDF)

    Args:
        topic: The research topic.
        auto_approve: If True, skip the plan review and execute immediately.

    Returns:
        The final report text.
    """
    graph = build_research_graph()

    initial_state = {
        "topic": topic,
        "plan_approved": False,
        "user_feedback": None,
        "research_plan": None,
        "report_sections": None,
        "section_research_findings": None,
        "research_evaluation": None,
        "current_goal": "",
        "parallel_goals": [],
        "parallel_findings": [],
        "research_iteration": 0,
        "iteration_count": 0,
        "max_iterations": config.max_search_iterations,
        "url_to_short_id": {},
        "sources": {},
        "final_cited_report": None,
        "final_report_with_citations": None,
        "messages": [],
        "errors": [],
        "evaluation_scores": [],
        "total_tokens": 0,
    }

    thread_id = f"research-{int(time.time())}"
    thread_config = {"configurable": {"thread_id": thread_id}}

    _print_banner(f"DEEP RESEARCH: {topic[:60]}")
    print(f"  Thread: {thread_id}")
    if auto_approve:
        print("  Mode: auto-approve (plan review skipped)")
    print(f"{'='*60}\n")

    final_state = None
    try:
        # ── Phase 1: Stream until the plan-review interrupt ──
        for event in graph.stream(initial_state, thread_config):
            if isinstance(event, dict) and "__interrupt__" in event:
                raw = event["__interrupt__"]

                # Navigate LangGraph's interrupt wrapping
                if isinstance(raw, (list, tuple)) and raw:
                    payload = raw[0]
                    payload = getattr(payload, "value", payload)
                else:
                    payload = raw

                plan = (payload or {}).get("research_plan", "")
                sections = (payload or {}).get("report_sections", "")

                if not auto_approve:
                    _display_plan(plan, sections)

                if auto_approve:
                    resume_value = {"plan_approved": True}
                else:
                    print("  Options:")
                    print("    yes       — Approve plan and start research")
                    print("    <text>    — Provide feedback to refine the plan")
                    print("    abort     — Cancel")
                    choice = input("  > ").strip().lower()

                    if choice == "yes":
                        resume_value = {"plan_approved": True}
                        print("\n  [Plan approved — starting research...]\n")
                    elif choice == "abort":
                        print("\n  [Research aborted]")
                        return ""
                    else:
                        resume_value = {"user_feedback": choice}
                        print(f"\n  [Feedback received — regenerating plan...]\n")

                # ── Phase 2: Resume with invoke (blocking, runs to completion) ──
                final_values = graph.invoke(Command(resume=resume_value), thread_config)

                # If feedback was given, the planner loops back to the interrupt.
                # Continue the outer for-loop to catch the new interrupt.
                if not resume_value.get("plan_approved"):
                    continue

                # Plan approved — final_values contains the final state
                final_state = final_values
                report = (
                    final_values.get("final_report_with_citations")
                    or final_values.get("final_cited_report")
                    or ""
                )
                break  # Exit the event loop

        else:
            # No interrupt fired: the graph may have completed without a stop
            final_state = graph.get_state(thread_config)
            report = (
                final_state.values.get("final_report_with_citations")
                or final_state.values.get("final_cited_report")
                or ""
            )

        # ── Report result ──
        if not report:
            print("\n  [WARNING] No report was generated.")
            if final_state and final_state.values.get("errors"):
                for err in final_state.values["errors"]:
                    print(f"    Error: {err}")
            return ""

        # Save markdown report (graceful degradation on save failure)
        md_path = None
        pdf_path = None
        try:
            output_dir = Path(config.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_topic = topic.replace(" ", "_").replace("/", "_")[:40]
            md_path = output_dir / f"report_{safe_topic}_{timestamp}.md"

            with open(md_path, "w") as f:
                f.write(report)

            # ── Generate PDF ──
            pdf_path = _convert_to_pdf(md_path)
        except (PermissionError, OSError) as e:
            logger.warning("Could not save report to file: %s — printing to stdout only", e)
            md_path = None
            pdf_path = None

        _print_banner("RESEARCH COMPLETE")
        if md_path:
            print(f"  Markdown: {md_path}")
        if pdf_path:
            print(f"  PDF:      {pdf_path}  ({pdf_path.stat().st_size:,} bytes)")
        if not md_path and not pdf_path:
            print(f"  Files:    (not saved — report follows below)")
        print(f"  Size:     {len(report):,} chars")
        total_tokens_val = final_state.values.get("total_tokens", 0) if final_state else 0
        if total_tokens_val:
            print(f"  Tokens:   {total_tokens_val:,}")
        print()
        for line in report.split("\n")[:20]:
            print(f"  {line}")
        if len(report.split("\n")) > 20:
            print(f"  ... [{len(report.split(chr(10))) - 20} more lines]")
        print()

        return report

    except KeyboardInterrupt:
        print("\n\n  [Research interrupted by user]")
        return ""
    except Exception as e:
        logger.exception("Research failed")
        # If we have a report in memory but file save failed, print it
        print(f"\n  [ERROR] Research failed: {e}")
        return ""


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Deep Research Agent — LangGraph-based multi-phase research"
    )
    parser.add_argument(
        "topic",
        nargs="?",
        help="Research topic (or use --topic-file)",
    )
    parser.add_argument(
        "--topic-file",
        type=str,
        help="Path to a file containing the research topic",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Auto-approve the research plan (skip interrupt)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Resolve topic
    topic = args.topic
    if not topic and args.topic_file:
        with open(args.topic_file) as f:
            topic = f.read().strip()
    if not topic:
        parser.print_help()
        print("\nError: Provide a research topic or --topic-file")
        sys.exit(1)

    run_research(topic, auto_approve=args.auto)


if __name__ == "__main__":
    _setup_logging()
    main()
