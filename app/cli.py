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


def run_research(topic: str, auto_approve: bool = False) -> str:
    """Execute full deep research workflow from the command line.

    Flow:
      1. Stream the graph to generate the plan → hits an interrupt for review
      2. Display plan, ask for user approval/feedback
      3. Resume with ``graph.invoke(Command(resume=...))`` — runs the rest
         of the pipeline (research → evaluation → composer)
      4. Save and return the final report

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
    }

    thread_id = f"research-{int(time.time())}"
    thread_config = {"configurable": {"thread_id": thread_id}}

    _print_banner(f"DEEP RESEARCH: {topic[:60]}")
    print(f"  Thread: {thread_id}")
    if auto_approve:
        print("  Mode: auto-approve (plan review skipped)")
    print(f"{'='*60}\n")

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
            if final_state.values.get("errors"):
                for err in final_state.values["errors"]:
                    print(f"    Error: {err}")
            return ""

        # Save report
        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_topic = topic.replace(" ", "_").replace("/", "_")[:40]
        filename = output_dir / f"report_{safe_topic}_{timestamp}.md"

        with open(filename, "w") as f:
            f.write(report)

        _print_banner("RESEARCH COMPLETE")
        print(f"  Report: {filename}")
        print(f"  Size: {len(report):,} chars\n")
        for line in report.split("\n")[:20]:
            print(f"  {line}")
        if len(report.split("\n")) > 20:
            print(f"  ... [{len(report.split('\n')) - 20} more lines]")
        print()

        return report

    except KeyboardInterrupt:
        print("\n\n  [Research interrupted by user]")
        return ""
    except Exception as e:
        logger.exception("Research failed")
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
