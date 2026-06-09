"""MCP server for the LangGraph deep research agent.

Exposes the research pipeline as an MCP tool so that any MCP client
(Hermes, Claude Code, Cursor, etc.) can invoke deep research.

Usage:
    # Run as HTTP+SSE server (for Docker deployment)
    python -m app.mcp_server --transport sse --port 8100

    # Run as stdio server (for Hermes mcp add --command)
    python -m app.mcp_server --transport stdio

Register in Hermes:
    hermes mcp add research --command "python -m app.mcp_server --transport stdio"
    # or for Docker:
    hermes mcp add research --url http://localhost:8100/mcp
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# MCP Server
# ──────────────────────────────────────────────

server = Server("deep-research")

# ── Background task store for long-running deep research
_research_tasks: dict[str, dict[str, Any]] = {}
_research_lock = asyncio.Lock()
_stream_queues: dict[str, asyncio.Queue[dict[str, Any]]] = {}
_stream_lock = asyncio.Lock()
_main_event_loop: asyncio.AbstractEventLoop | None = None  # Set at server startup

# Human-readable labels for pipeline stages
STAGE_LABELS: dict[str, str] = {
    "planning": "Generating research plan",
    "planner": "Generating research plan",
    "parallel_researcher": "Searching the web (Phase 1)",
    "merge_findings": "Synthesizing search findings",
    "refinement_loop": "Refining with deeper research (Phase 2)",
    "composer": "Writing the final report",
    "report_critic": "Running final report QA",
    "saving": "Saving report to disk",
    "saving_pdf": "Generating PDF",
    "error": "Error",
}
_TASK_TTL_SECONDS = 86400  # 24 hours — tasks survive between restarts


def _get_report_dir() -> Path:
    """Return the first writable report directory from the fallback chain.

    Order: RESEARCH_OUTPUT_DIR env → ~/research → current directory.
    """
    env_report_dir = os.getenv("RESEARCH_OUTPUT_DIR")
    candidates = []
    if env_report_dir:
        candidates.append(Path(env_report_dir))
    candidates.extend([
        Path.home() / "research",
        Path.cwd(),
    ])
    for candidate in candidates:
        if not candidate:
            continue
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            # Verify writable
            test_file = candidate / ".write_test"
            test_file.write_text("ok")
            test_file.unlink()
            return candidate
        except (PermissionError, OSError):
            continue
    # Should never reach here (cwd is always writable), but satisfy type checker
    return Path.cwd()


def _persist_task(task: dict) -> None:
    """Save completed task metadata to disk so it survives restarts."""
    import json as _json
    report_dir = _get_report_dir()
    meta_file = report_dir / f"task_{task['task_id']}.json"
    # Strip report text from disk copy (report is already in the .md file)
    disk_task = {k: v for k, v in task.items() if k != "report"}
    with open(meta_file, "w") as f:
        _json.dump(disk_task, f)


def _load_persisted_task(task_id: str) -> dict | None:
    """Load completed task metadata from disk fallback."""
    import json as _json
    report_dir = _get_report_dir()
    meta_file = report_dir / f"task_{task_id}.json"
    if not meta_file.exists():
        return None
    try:
        with open(meta_file) as f:
            task = _json.load(f)
        # Read report from disk
        report_path = task.get("report_path", "")
        if report_path and Path(report_path).exists():
            with open(report_path) as f:
                task["report"] = f.read()
        return task
    except Exception:
        return None


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """Declare the available research tools."""
    return [
        types.Tool(
            name="search",
            description="""Quick web search via SearXNG (Google/Bing/DuckDuckGo aggregated).

Returns a list of results with title, URL, and snippet for each.

Use this for: quick fact-finding, looking up specific URLs, finding recent
articles or documentation, checking product availability, price checks,
and any question answerable with a single search.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query — be specific.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of results to return (default: 5, max: 15).",
                        "default": 5,
                    },
                    "language": {
                        "type": "string",
                        "description": "Optional language hint (e.g. Spanish, German, es, de).",
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="deep_research",
            description="""Run a deep, multi-phase research investigation on any topic.

HOW IT WORKS:
1. Generates a structured research plan with [RESEARCH] and [DELIVERABLE] goals
2. Executes N parallel web searches per goal via SearXNG
3. Quality-checks findings with a numeric rubric (source_quality, claim_verification, completeness)
4. If quality < threshold, runs follow-up searches to fill gaps
5. Synthesizes everything into a fully cited markdown report with per-claim confidence levels

IMPORTANT: This tool returns immediately with a task_id. Use research_status(task_id)
to check progress and retrieve the final report. Research runs in background
and typically completes in 1-5 minutes. Polling every 10-15 seconds is
recommended until status is "completed" or "failed".

STREAMING: For real-time progress, connect to SSE endpoint after receiving task_id:
  GET /stream/{task_id}
Events: started, update (progress/stage), completed, failed, heartbeat.

TOPIC GUIDANCE:
- Be specific and contextual: "Compare LangGraph vs CrewAI for production multi-agent systems in 2026" works better than "AI agent frameworks"
- Include time context if relevant (year, "current", "latest")

USE FOR: competitive analysis, market research, technical deep-dives,
regulatory reviews, vendor ecosystem mapping, literature surveys.
NOT FOR: simple fact lookups (use search tool), real-time data (stock prices, weather).""",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "The research topic — be specific and contextual.",
                    },
                    "max_iterations": {
                        "type": "integer",
                        "description": "Max critique-refinement loops (default: 2, range: 1-5). Lower for faster results.",
                        "default": 2,
                    },
                    "depth": {
                        "type": "string",
                        "description": "Report depth: 'brief' (2-3 paragraph summary, 30-60s) or 'standard' (full report, 2-5 min). Default: standard.",
                        "default": "standard",
                    },
                    "pdf": {
                        "type": "boolean",
                        "description": "Also generate a PDF version of the report (requires pandoc + weasyprint). Default: false.",
                        "default": False,
                    },
                },
                "required": ["topic"],
            },
        ),
        types.Tool(
            name="research_status",
            description="""Check the status of a running deep_research task.

Takes a task_id returned by deep_research and returns:
- status: "running" | "completed" | "failed"
- progress: 0.0 to 1.0 (only when running)
- report: the full markdown report (when completed)
- error: error message (when failed)
- topic, timestamp, report_path metadata

Poll this until status is "completed" or "failed". Research typically
takes 1-5 minutes.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The task_id returned by deep_research",
                    },
                },
                "required": ["task_id"],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict[str, Any] | None
) -> list[types.TextContent | types.EmbeddedResource]:
    """Execute a research or search tool."""
    if name == "search":
        return await _handle_search(arguments)
    elif name == "deep_research":
        return await _handle_deep_research(arguments)
    elif name == "research_status":
        return await _handle_research_status(arguments)
    else:
        raise ValueError(f"Unknown tool: {name}")


async def _handle_search(
    arguments: dict[str, Any] | None
) -> list[types.TextContent | types.EmbeddedResource]:
    """Quick web search using the configured backend chain."""
    from app.tools.search import format_search_results, get_search_tool

    query = (arguments or {}).get("query", "")
    max_results = min(int((arguments or {}).get("max_results", 5)), 15)
    language = (arguments or {}).get("language")

    if not query:
        return [types.TextContent(type="text", text="Error: 'query' is required.")]

    try:
        search_tool = get_search_tool()
        results = await asyncio.to_thread(
            search_tool.invoke,
            {"query": query, "max_results": max_results, "language": language},
        )
    except Exception as e:
        return [
            types.TextContent(
                type="text",
                text=f"Search failed: {e}\n\nCheck your configured search backend and network connectivity.",
            )
        ]

    if not results:
        return [types.TextContent(type="text", text=f"No results found for: {query}")]

    return [types.TextContent(type="text", text=format_search_results(query, results))]


def _push_stream_event(task_id: str, event: dict[str, Any]) -> None:
    """Push a progress event to the SSE stream queue for a task (thread-safe)."""
    # Use the stored event loop from server startup — get_event_loop()
    # fails in background threads on Python 3.12+
    loop = _main_event_loop
    if loop is None:
        return
    if task_id in _stream_queues:
        q = _stream_queues[task_id]
        loop.call_soon_threadsafe(q.put_nowait, event)


def _deep_research_runner(task_id: str, topic: str, max_iterations: int, depth: str = "standard", pdf: bool = False):
    """Run the full research pipeline in background thread, updating _research_tasks.

    Runs in a thread because graph.invoke() is synchronous and would block
    the asyncio event loop.
    """
    import time
    from app.agent import build_research_graph
    from app.nodes.planner import generate_plan_only

    def _update(task_id: str, **kwargs):
        """Update task dict and push stream event."""
        task = _research_tasks.get(task_id)
        if task:
            task.update(kwargs)
        _push_stream_event(task_id, {"event": "update", "task_id": task_id, **kwargs})

    task = _research_tasks.get(task_id)
    if task:
        task["status"] = "running"
        task["progress"] = 0.05
        task["stage"] = "planning"

    try:
        graph = build_research_graph()
        initial_state = {
            "topic": topic, "plan_approved": True, "user_feedback": None,
            "research_plan": None, "report_sections": None,
            "report_blueprint": None,
            "section_research_findings": None, "research_evaluation": None,
            "sufficiency_assessment": None,
            "current_goal": "", "parallel_goals": [], "parallel_findings": [],
            "research_iteration": 0, "iteration_count": 0,
            "max_iterations": max_iterations,
            "url_to_short_id": {}, "sources": {},
            "evidence_claims": [], "evidence_gaps": [],
            "final_cited_report": None, "final_report_with_citations": None,
            "report_critic_result": None, "report_critic_passed": False,
            "messages": [], "errors": [], "evaluation_scores": [],
            "total_tokens": 0, "cached_goal_count": 0,
            "depth": depth,
        }
        thread_id = task_id
        thread_config = {"configurable": {"thread_id": thread_id}}

        # Generate plan
        plan_result = generate_plan_only(topic)
        initial_state["research_plan"] = plan_result["research_plan"]
        initial_state["report_sections"] = plan_result["report_sections"]
        initial_state["report_blueprint"] = plan_result.get("report_blueprint")
        initial_state["parallel_goals"] = plan_result["parallel_goals"]
        initial_state["plan_approved"] = True
        if plan_result.get("total_tokens"):
            initial_state["total_tokens"] = plan_result["total_tokens"]

        _update(task_id, status="running", progress=0.2, stage="planning")

        # Run graph with streaming for progress tracking
        node_progress = {
            "__start__": 0.0,
            "planner": 0.1,
            "parallel_researcher": 0.25,
            "merge_findings": 0.45,
            "refinement_loop": 0.65,
            "composer": 0.85,
            "report_critic": 0.93,
            "__end__": 1.0,
        }

        report = ""
        report_critic_result = None
        report_critic_passed = False
        for event in graph.stream(initial_state, thread_config):
            for node_name in event:
                if node_name in node_progress:
                    _update(task_id, progress=node_progress[node_name], stage=node_name)

                # Extract report when composer finishes
                if isinstance(event.get(node_name), dict):
                    node_data = event[node_name]
                    if isinstance(node_data, dict):
                        rpt = node_data.get("final_report_with_citations") or node_data.get("final_cited_report") or ""
                        if rpt:
                            report = rpt
                        if "report_critic_result" in node_data:
                            report_critic_result = node_data.get("report_critic_result")
                        if "report_critic_passed" in node_data:
                            report_critic_passed = bool(node_data.get("report_critic_passed"))

        if not report:
            err_text = "No report was generated. Check logs for details."
            _update(task_id, status="failed", error=err_text, progress=1.0, stage="error")
            failed_task = _research_tasks.get(task_id)
            if failed_task:
                failed_task["completed_at"] = time.time()
                _persist_task(failed_task)
            return

        # Save report
        report_dir = _get_report_dir()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_topic = topic.replace(" ", "_").replace("/", "_")[:40]
        filename = report_dir / f"report_{safe_topic}_{timestamp}_{task_id[-12:]}.md"
        with open(filename, "w") as f:
            f.write(report)

        _update(task_id, progress=0.95, stage="saving")

        # Generate PDF if requested
        pdf_path = None
        if pdf:
            try:
                from app.cli import _convert_to_pdf
                pdf_path = _convert_to_pdf(filename)
                if pdf_path:
                    _update(task_id, stage="saving_pdf")
            except Exception as e:
                logger.warning("PDF generation failed for task %s: %s", task_id, e)

        if task:
            task["status"] = "completed"
            task["progress"] = 1.0
            task["report"] = report
            task["report_path"] = str(filename)
            task["pdf_path"] = str(pdf_path) if pdf_path else None
            task["char_count"] = len(report)
            task["report_critic_result"] = report_critic_result
            task["report_critic_passed"] = report_critic_passed
            task["stage"] = "report_critic"
            task["completed_at"] = time.time()
            _persist_task(task)

        _push_stream_event(task_id, {
            "event": "completed",
            "task_id": task_id,
            "status": "completed",
            "progress": 1.0,
            "report_path": str(filename),
            "char_count": len(report),
        })

    except Exception as e:
        logger.exception("Background research failed for task %s", task_id)
        _update(task_id, status="failed", error=str(e), progress=1.0, stage="error")
        failed_task = _research_tasks.get(task_id)
        if failed_task:
            import time
            failed_task["completed_at"] = time.time()
            _persist_task(failed_task)


async def _handle_deep_research(
    arguments: dict[str, Any] | None
) -> list[types.TextContent]:
    """Start deep research in background, return task_id immediately."""
    import time, uuid

    topic = (arguments or {}).get("topic", "")
    max_iterations = max(1, min(int((arguments or {}).get("max_iterations", 2)), 10))
    depth = (arguments or {}).get("depth", "standard")
    pdf = (arguments or {}).get("pdf", False)
    if isinstance(pdf, str):
        pdf = pdf.lower() in ("true", "1", "yes")

    if depth not in ("brief", "standard"):
        depth = "standard"

    if not topic:
        return [types.TextContent(type="text", text="Error: 'topic' is required.")]

    task_id = f"research-{uuid.uuid4().hex[:12]}"
    now = time.time()

    async with _research_lock:
        _research_tasks[task_id] = {
            "task_id": task_id,
            "topic": topic,
            "status": "queued",
            "progress": 0.0,
            "created_at": now,
            "max_iterations": max_iterations,
            "depth": depth,
            "pdf": pdf,
        }

    # Cleanup stale tasks (>1 hour old)
    async with _research_lock:
        stale = [tid for tid, t in _research_tasks.items()
                 if now - t.get("created_at", now) > _TASK_TTL_SECONDS]
        for tid in stale:
            del _research_tasks[tid]

    # Launch background task in thread (sync graph.invoke blocks asyncio event loop)
    asyncio.create_task(asyncio.to_thread(_deep_research_runner, task_id, topic, max_iterations, depth, pdf))

    return [types.TextContent(
        type="text",
        text=f"""## Research Started

**Task ID:** {task_id}
**Topic:** {topic}
**Max iterations:** {max_iterations}
**Status:** queued -> running in background

Poll with research_status("{task_id}") every 10-15 seconds until status is "completed".
Research typically completes in 1-5 minutes.

Example: research_status(task_id="{task_id}")"""
    )]


async def _handle_research_status(
    arguments: dict[str, Any] | None
) -> list[types.TextContent]:
    """Check the status of a background research task."""
    task_id = (arguments or {}).get("task_id", "")

    if not task_id:
        return [types.TextContent(type="text", text="Error: 'task_id' is required.")]

    async with _research_lock:
        task = _research_tasks.get(task_id)

    if not task:
        # Try disk fallback (survives restarts and TTL cleanup)
        task = await asyncio.to_thread(_load_persisted_task, task_id)

    if not task:
        return [types.TextContent(
            type="text",
            text=f"## Task Not Found\n\nTask ID `{task_id}` not found in memory or on disk.\nIt may never have existed, or the report file was deleted.\n\nCheck `/data/` (in container) or `RESEARCH_OUTPUT_DIR` for saved reports."
        )]

    status = task["status"]
    import time

    if status == "queued" or status == "running":
        elapsed = time.time() - task.get("created_at", time.time())
        stage = task.get("stage", "")
        stage_label = STAGE_LABELS.get(stage, stage)
        progress_pct = task.get("progress", 0)
        return [types.TextContent(
            type="text",
            text=f"""## Research In Progress

**Task ID:** {task_id}
**Topic:** {task.get("topic", "")}
**Status:** {status}
**Stage:** {stage_label} ({progress_pct:.0%})
**Elapsed:** {_format_elapsed_minutes(elapsed)}

Poll again in 10-15 seconds."""
        )]

    elif status == "completed":
        report = task.get("report", "")
        qa_status = "pass" if task.get("report_critic_passed") else "fail"
        return [types.TextContent(
            type="text",
            text=f"""## Research Complete

**Task ID:** {task_id}
**Topic:** {task.get("topic", "")}
**Report QA:** {qa_status}
**Report saved:** {task.get("report_path", "")}
**PDF:** {task.get("pdf_path") or "not generated"}
**Size:** {task.get("char_count", 0):,} chars

---

{report}"""
        )]

    elif status == "failed":
        return [types.TextContent(
            type="text",
            text=f"""## Research Failed

**Task ID:** {task_id}
**Topic:** {task.get("topic", "")}
**Error:** {task.get("error", "Unknown error")}"""
        )]

    return [types.TextContent(type="text", text=f"Unknown status: {status}")]


# ──────────────────────────────────────────────
# CLI Entry
# ──────────────────────────────────────────────


async def _run_stdio():
    """Run with stdio transport (for local subprocess spawning)."""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="deep-research",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def _load_persisted_task_meta(meta_file: Path) -> dict[str, Any] | None:
    """Load task metadata from a persisted task JSON file."""
    import json as _json

    try:
        with open(meta_file) as f:
            return _json.load(f)
    except Exception:
        return None



def _list_persisted_tasks(limit: int = 100) -> list[dict[str, Any]]:
    """Return persisted task metadata sorted newest-first."""
    report_dir = _get_report_dir()
    tasks: list[dict[str, Any]] = []
    for meta_file in sorted(
        report_dir.glob('task_*.json'),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ):
        task = _load_persisted_task_meta(meta_file)
        if task:
            tasks.append(task)
        if len(tasks) >= limit:
            break
    return tasks



def _hydrate_task_cache_from_disk(limit: int = 100) -> None:
    """Merge persisted terminal tasks into the in-memory task cache."""
    for task in _list_persisted_tasks(limit=limit):
        task_id = task.get('task_id')
        if task_id and task_id not in _research_tasks:
            _research_tasks[task_id] = task



def _format_elapsed_minutes(seconds: float) -> str:
    """Format elapsed time for user-facing UI labels in minutes."""
    minutes = max(seconds, 0) / 60
    return f"{minutes:.1f}m" if minutes < 10 else f"{minutes:.0f}m"


def _task_api_view(task: dict[str, Any], now: float) -> dict[str, Any]:
    """Project internal task state into the dashboard/API response shape."""
    stage_raw = task.get('stage', '')
    created_at = task.get('created_at', task.get('completed_at', now))
    is_terminal = task.get('status') in {'completed', 'failed'}
    completed_at = task.get('completed_at') if is_terminal else None
    elapsed = int(max(((completed_at if completed_at is not None else now) - created_at) if is_terminal else (now - created_at), 0))
    report_path = task.get('report_path', '')
    pdf_path = task.get('pdf_path')
    return {
        'task_id': task.get('task_id', ''),
        'topic': task.get('topic', ''),
        'status': task.get('status', 'unknown'),
        'progress': task.get('progress', 0),
        'stage': STAGE_LABELS.get(stage_raw, stage_raw),
        'elapsed': elapsed,
        'has_report': bool(report_path),
        'report_filename': Path(report_path).name if report_path else '',
        'has_pdf': bool(pdf_path),
        'pdf_filename': Path(pdf_path).name if pdf_path else '',
        'char_count': task.get('char_count', 0),
        'report_critic_passed': task.get('report_critic_passed'),
        'report_critic_result': task.get('report_critic_result'),
    }



def _list_all_tasks(limit: int = 100) -> list[dict[str, Any]]:
    """Return merged in-memory + persisted tasks for the dashboard."""
    import time as _time_module

    tasks_by_id: dict[str, dict[str, Any]] = {
        task['task_id']: task for task in _list_persisted_tasks(limit=limit)
        if task.get('task_id')
    }
    for task_id, task in _research_tasks.items():
        tasks_by_id[task_id] = {**tasks_by_id.get(task_id, {}), **task}

    now = _time_module.time()
    ordered = sorted(
        tasks_by_id.values(),
        key=lambda t: t.get('created_at', t.get('completed_at', 0)),
        reverse=True,
    )
    return [_task_api_view(task, now) for task in ordered[:limit]]



def _probe_report_dir() -> dict[str, Any]:
    """Verify that the report directory is writable."""
    try:
        report_dir = _get_report_dir().resolve()
        return {'ok': True, 'detail': str(report_dir)}
    except Exception as e:
        return {'ok': False, 'detail': str(e)}



def _probe_checkpoint_db() -> dict[str, Any]:
    """Verify that the checkpoint DB path is writable/openable."""
    import sqlite3

    try:
        db_path = Path(os.getenv('CHECKPOINT_DB_PATH', 'checkpoints.db')).expanduser()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.execute('PRAGMA schema_version;')
        conn.close()
        return {'ok': True, 'detail': str(db_path)}
    except Exception as e:
        return {'ok': False, 'detail': str(e)}



def _probe_llm_api() -> dict[str, Any]:
    """Verify that the configured LLM endpoint is reachable."""
    import httpx
    from app.config import ResearchConfig

    runtime_config = ResearchConfig()
    if not runtime_config.worker_api_key or not runtime_config.worker_api_base:
        return {'ok': False, 'detail': 'WORKER_API_KEY / WORKER_API_BASE missing'}

    endpoint = runtime_config.worker_api_base.rstrip('/') + '/models'
    headers = {'Authorization': f'Bearer {runtime_config.worker_api_key}'}
    try:
        with httpx.Client(timeout=3.0, follow_redirects=True) as client:
            resp = client.get(endpoint, headers=headers)
        if 200 <= resp.status_code < 300:
            return {'ok': True, 'detail': f'{endpoint} ({resp.status_code})'}
        return {'ok': False, 'detail': f'{endpoint} ({resp.status_code})'}
    except Exception as e:
        return {'ok': False, 'detail': str(e)}



def _probe_search_backend() -> dict[str, Any]:
    """Verify that the active search path can execute a real low-cost query."""
    from app.tools.search import _DEFAULT_SEARXNG_URL

    if os.getenv('TAVILY_API_KEY'):
        try:
            from langchain_community.tools.tavily_search import TavilySearchResults

            tool = TavilySearchResults(max_results=1)
            tool.invoke({'query': 'health check'})
            return {'ok': True, 'detail': 'tavily'}
        except Exception as e:
            return {'ok': False, 'detail': f'tavily: {e}'}

    searxng_url = os.getenv('SEARXNG_URL', _DEFAULT_SEARXNG_URL)
    try:
        import httpx

        with httpx.Client(timeout=3.0) as client:
            resp = client.get(f"{searxng_url.rstrip('/')}/search?q=health&format=json")
        if resp.status_code == 200:
            return {'ok': True, 'detail': searxng_url}
        return {'ok': False, 'detail': f'{searxng_url} ({resp.status_code})'}
    except Exception:
        pass

    try:
        from ddgs import DDGS

        with DDGS() as ddgs:
            list(ddgs.text('health check', max_results=1, region='us-en'))
        return {'ok': True, 'detail': 'ddgs fallback'}
    except Exception as e:
        return {'ok': False, 'detail': f'ddgs: {e}'}



def _build_readiness_payload() -> tuple[dict[str, Any], int]:
    """Compute readiness status and HTTP code."""
    from app.config import ResearchConfig

    runtime_config = ResearchConfig()
    issues = runtime_config.validate()
    critical_issues = [
        issue for issue in issues
        if 'WORKER_API_KEY' in issue or 'WORKER_API_BASE' in issue
    ]
    checks = {
        'config': {
            'ok': not critical_issues,
            'detail': 'configured' if not critical_issues else '; '.join(critical_issues),
        },
        'report_dir': _probe_report_dir(),
        'checkpoint_db': _probe_checkpoint_db(),
        'llm_api': _probe_llm_api(),
        'search_backend': _probe_search_backend(),
    }
    ok = all(check['ok'] for check in checks.values())
    payload = {'status': 'ok' if ok else 'degraded', 'server': 'deep-research', 'checks': checks}
    return payload, 200 if ok else 503



def _mcp_tools_payload() -> list[dict[str, Any]]:
    """Shared MCP tool metadata for POST /mcp tools/list."""
    return [
        {
            'name': 'search',
            'description': 'Quick web search via SearXNG (Google/Bing/DuckDuckGo aggregated). Returns title, URL, and snippet.',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'The search query'},
                    'max_results': {'type': 'integer', 'description': 'Max results (default: 5, max: 15)', 'default': 5},
                    'language': {'type': 'string', 'description': 'Optional language hint (e.g. Spanish, German, es, de).'},
                },
                'required': ['query'],
            },
        },
        {
            'name': 'deep_research',
            'description': 'Run a deep, multi-phase research investigation on any topic. Returns a task_id immediately — poll with research_status(task_id) for results.',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'topic': {'type': 'string', 'description': 'The research topic'},
                    'max_iterations': {'type': 'integer', 'description': 'Max critique-refinement loops (default: 2)', 'default': 2},
                    'depth': {'type': 'string', 'description': 'Report depth: brief or standard', 'default': 'standard'},
                    'pdf': {'type': 'boolean', 'description': 'Also generate a PDF version of the report', 'default': False},
                },
                'required': ['topic'],
            },
        },
        {
            'name': 'research_status',
            'description': "Check the status of a deep_research task. Returns 'running'/'completed'/'failed' with progress, report, or error.",
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'task_id': {'type': 'string', 'description': 'Task ID from deep_research'},
                },
                'required': ['task_id'],
            },
        },
    ]



def create_http_app(sse=None):
    """Create the Starlette HTTP app for MCP, dashboard, and health endpoints."""
    from starlette.applications import Starlette
    from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
    from starlette.routing import Mount, Route

    def _dashboard_access_allowed(request) -> bool:
        import ipaddress

        def _is_local_network_ip(value: str) -> bool:
            try:
                ip = ipaddress.ip_address(value)
            except ValueError:
                return False
            if ip.is_loopback:
                return True
            if ip.version == 4:
                return any(ip in ipaddress.ip_network(net) for net in (
                    '10.0.0.0/8',
                    '172.16.0.0/12',
                    '192.168.0.0/16',
                ))
            return ip in ipaddress.ip_network('fc00::/7')

        if os.getenv('DASHBOARD_PUBLIC', '').lower() in {'1', 'true', 'yes'}:
            return True
        client_host = getattr(getattr(request, 'client', None), 'host', '')
        if client_host in {'localhost', 'testclient'}:
            return True
        return _is_local_network_ip(client_host)

    def _dashboard_forbidden():
        return JSONResponse({'error': 'Forbidden'}, status_code=403)

    _hydrate_task_cache_from_disk(limit=100)

    async def handle_sse(request):
        if sse is None:
            return JSONResponse({'error': 'SSE transport unavailable'}, status_code=503)
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await server.run(
                streams[0],
                streams[1],
                InitializationOptions(
                    server_name='deep-research',
                    server_version='0.1.0',
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
        return Response()

    async def health_check(request):
        return JSONResponse({'status': 'ok', 'server': 'deep-research'})

    async def ready_check(request):
        payload, status_code = _build_readiness_payload()
        return JSONResponse(payload, status_code=status_code)

    async def mcp_probe(request):
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Parse error'}})

        method = body.get('method', '')
        request_id = body.get('id', 0)

        if method == 'initialize':
            return JSONResponse({
                'jsonrpc': '2.0',
                'id': request_id,
                'result': {
                    'protocolVersion': '2024-11-05',
                    'serverInfo': {'name': 'deep-research', 'version': '0.1.0'},
                    'capabilities': {'tools': {}, 'resources': {}},
                },
            })
        if method == 'tools/list':
            return JSONResponse({'jsonrpc': '2.0', 'id': request_id, 'result': {'tools': _mcp_tools_payload()}})
        if method == 'tools/call':
            tool_name = body.get('params', {}).get('name', '')
            tool_args = body.get('params', {}).get('arguments', {})
            try:
                result = await handle_call_tool(tool_name, tool_args)
                content = []
                for item in result:
                    if isinstance(item, types.TextContent):
                        content.append({'type': 'text', 'text': item.text})
                    elif isinstance(item, types.EmbeddedResource):
                        content.append({'type': 'resource', 'resource': {
                            'uri': str(item.resource.uri) if hasattr(item.resource, 'uri') else '',
                            'mimeType': item.resource.mimeType if hasattr(item.resource, 'mimeType') else 'text/markdown',
                        }})
                return JSONResponse({'jsonrpc': '2.0', 'id': request_id, 'result': {'content': content, 'isError': False}})
            except Exception as e:
                logger.exception('tools/call failed via POST')
                return JSONResponse({
                    'jsonrpc': '2.0',
                    'id': request_id,
                    'result': {'content': [{'type': 'text', 'text': f'Tool execution failed: {e}'}], 'isError': True},
                })
        if method == 'notifications/initialized':
            return JSONResponse({'jsonrpc': '2.0', 'id': request_id, 'result': {}})
        return JSONResponse({'jsonrpc': '2.0', 'id': request_id, 'error': {'code': -32601, 'message': f'Method not found: {method}'}})

    async def handle_stream(request):
        if not _dashboard_access_allowed(request):
            return _dashboard_forbidden()

        task_id = request.path_params.get('task_id', '')
        if not task_id:
            return JSONResponse({'error': 'task_id required'}, status_code=400)

        task = _research_tasks.get(task_id)
        if not task:
            task = await asyncio.to_thread(_load_persisted_task, task_id)
        if not task:
            return JSONResponse({'error': 'Task not found'}, status_code=404)

        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        async with _stream_lock:
            _stream_queues[task_id] = q

        task_snapshot = dict(task)

        async def event_generator():
            import json as _json

            yield f"event: started\ndata: {_json.dumps({'task_id': task_id, 'topic': task_snapshot.get('topic', ''), 'status': task_snapshot.get('status', 'running'), 'progress': task_snapshot.get('progress', 0)})}\n\n".encode('utf-8')

            if task_snapshot.get('status') in ('completed', 'failed'):
                yield f"event: {task_snapshot['status']}\ndata: {_json.dumps({'task_id': task_id, 'status': task_snapshot['status'], 'progress': task_snapshot.get('progress', 1.0)})}\n\n".encode('utf-8')
                async with _stream_lock:
                    _stream_queues.pop(task_id, None)
                return

            last_progress = task_snapshot.get('progress', 0)
            completed = False
            while not completed:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=5.0)
                    yield f"event: {event.get('event', 'update')}\ndata: {_json.dumps(event)}\n\n".encode('utf-8')
                    if event.get('event') in ('completed', 'failed'):
                        completed = True
                        break
                except asyncio.TimeoutError:
                    current_task = _research_tasks.get(task_id)
                    if current_task:
                        current_progress = current_task.get('progress', last_progress)
                        if current_progress != last_progress:
                            last_progress = current_progress
                            yield f"event: heartbeat\ndata: {_json.dumps({'task_id': task_id, 'progress': current_progress, 'status': current_task.get('status', 'running')})}\n\n".encode('utf-8')
                        if current_task.get('status') in ('completed', 'failed'):
                            yield f"event: {current_task['status']}\ndata: {_json.dumps({'task_id': task_id, 'status': current_task['status'], 'progress': 1.0})}\n\n".encode('utf-8')
                            completed = True
                    else:
                        yield f"event: completed\ndata: {_json.dumps({'task_id': task_id, 'status': 'completed', 'progress': 1.0})}\n\n".encode('utf-8')
                        completed = True

            async with _stream_lock:
                _stream_queues.pop(task_id, None)

        return StreamingResponse(
            event_generator(),
            media_type='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no',
            },
        )

    async def tasks_api(request):
        if not _dashboard_access_allowed(request):
            return _dashboard_forbidden()
        return JSONResponse(_list_all_tasks())

    async def dashboard(request):
        if not _dashboard_access_allowed(request):
            return _dashboard_forbidden()
        html = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Deep Research — Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;background:#0d1117;color:#c9d1d9;padding:2rem;min-height:100vh}
h1{font-size:1.5rem;margin-bottom:.25rem;color:#f0f6fc}
.subtitle{color:#8b949e;margin-bottom:2rem;font-size:.9rem}
.task{border:1px solid #30363d;border-radius:8px;padding:1.25rem;margin-bottom:1rem;background:#161b22}
.task-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:.75rem}
.task-topic{font-weight:600;color:#f0f6fc;flex:1;margin-right:1rem}
.task-id{font-size:.75rem;color:#484f58;font-family:monospace}
.progress-bar{width:100%;height:6px;background:#21262d;border-radius:3px;margin:.5rem 0 .75rem;overflow:hidden}
.progress-fill{height:100%;border-radius:3px;transition:width .5s ease}
.progress-fill.running{background:#238636}
.progress-fill.completed{background:#1f6feb}
.progress-fill.failed{background:#da3633}
.progress-fill.queued{background:#484f58}
.task-meta{display:flex;gap:1.5rem;font-size:.85rem;color:#8b949e;flex-wrap:wrap}
.task-meta span{display:flex;align-items:center;gap:.35rem}
.status-badge{display:inline-block;padding:.15rem .55rem;border-radius:12px;font-size:.75rem;font-weight:600}
.status-badge.running{background:#238636;color:#fff}
.status-badge.completed{background:#1f6feb;color:#fff}
.status-badge.failed{background:#da3633;color:#fff}
.status-badge.queued{background:#484f58;color:#c9d1d9}
.report-link{display:inline-block;margin-top:.75rem;color:#58a6ff;text-decoration:none;font-size:.85rem;cursor:pointer}
.report-link:hover{text-decoration:underline}
.empty{text-align:center;color:#484f58;padding:3rem;font-size:1.1rem}
.error-msg{text-align:center;color:#da3633;padding:3rem;font-size:1rem}
.indicator{width:8px;height:8px;border-radius:50%;display:inline-block}
.indicator.running{background:#238636;animation:pulse 1.5s ease-in-out infinite}
.indicator.completed{background:#1f6feb}
.indicator.failed{background:#da3633}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.refresh{color:#8b949e;font-size:.8rem;margin-top:1.5rem;text-align:center}
.modal-overlay{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:100;align-items:center;justify-content:center}
.modal-overlay.active{display:flex}
.modal{background:#161b22;border:1px solid #30363d;border-radius:8px;max-width:900px;max-height:85vh;width:90%;overflow:hidden;display:flex;flex-direction:column}
.modal-header{display:flex;justify-content:space-between;align-items:center;padding:1rem 1.25rem;border-bottom:1px solid #30363d}
.modal-header h2{font-size:1rem;color:#f0f6fc;margin:0}
.modal-close{background:none;border:none;color:#8b949e;font-size:1.5rem;cursor:pointer;line-height:1}
.modal-close:hover{color:#f0f6fc}
.modal-body{overflow-y:auto;padding:1.25rem;flex:1}
.modal-body pre{white-space:pre-wrap;font-family:monospace;font-size:.85rem;line-height:1.6;color:#c9d1d9;margin:0}
.modal-loading{padding:2rem;text-align:center;color:#8b949e}
.new-research{margin-bottom:2rem;padding:1.25rem;background:#161b22;border:1px solid #30363d;border-radius:8px}
.new-research h3{font-size:.9rem;color:#f0f6fc;margin-bottom:.75rem}
.form-row{display:flex;gap:.75rem;align-items:flex-end;flex-wrap:wrap}
.form-group{display:flex;flex-direction:column;gap:.3rem}
.form-group label{font-size:.75rem;color:#8b949e}
.form-group input,.form-group select{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:.5rem .75rem;color:#c9d1d9;font-size:.85rem;outline:none}
.form-group input:focus,.form-group select:focus{border-color:#1f6feb}
.form-group input{min-width:400px}
.form-group select{min-width:130px}
.btn{background:#238636;color:#fff;border:none;border-radius:6px;padding:.5rem 1.25rem;font-size:.85rem;font-weight:600;cursor:pointer;white-space:nowrap}
.btn:hover{background:#2ea043}
.btn:disabled{background:#484f58;cursor:not-allowed}
.feedback{font-size:.8rem;margin-top:.5rem;min-height:1.2em}
.feedback.success{color:#238636}
.feedback.error{color:#da3633}
</style>
</head>
<body>
<h1>Deep Research • Dashboard</h1>
<p class="subtitle">Monitor research tasks — auto-refreshes every 5s</p>
<div class="new-research">
  <h3>New Research</h3>
  <div class="form-row">
    <div class="form-group">
      <label for="topic">Topic</label>
      <input type="text" id="topic" placeholder="e.g. Kubernetes vs Nomad for small teams 2026" autofocus onkeydown="if(event.key==='Enter')startResearch()">
    </div>
    <div class="form-group">
      <label for="depth">Depth</label>
      <select id="depth">
        <option value="standard">Standard</option>
        <option value="brief">Brief</option>
      </select>
    </div>
    <div class="form-group" style="justify-content:flex-end">
      <label style="display:flex;align-items:center;gap:.4rem;cursor:pointer">
        <input type="checkbox" id="pdf" style="min-width:auto;accent-color:#238636"> PDF
      </label>
    </div>
    <button class="btn" id="start-btn" onclick="startResearch()">Start Research</button>
  </div>
  <div class="feedback" id="feedback"></div>
</div>
<div id="tasks"><p class="empty">Loading tasks…</p></div>
<p class="refresh" id="last-update">Last updated: —</p>
<div class="modal-overlay" id="modal-overlay" onclick="if(event.target===this)closeModal()">
  <div class="modal">
    <div class="modal-header">
      <h2 id="modal-title">Report</h2>
      <button class="modal-close" onclick="closeModal()">&times;</button>
    </div>
    <div class="modal-body" id="modal-body">
      <p class="modal-loading">Loading report…</p>
    </div>
  </div>
</div>
<script>
let fetchErrorCount = 0;
function formatElapsedMinutes(seconds) {
  const mins = Math.max(seconds, 0) / 60;
  return (mins < 10 ? mins.toFixed(1) : Math.round(mins).toString()) + 'm';
}
async function refresh() {
  try {
    const resp = await fetch('/tasks');
    if(!resp.ok) throw new Error('HTTP '+resp.status);
    const tasks = await resp.json();
    fetchErrorCount = 0;
    const el = document.getElementById('tasks');
    if(!tasks.length) {
      el.innerHTML = '<p class="empty">No research tasks yet.<br><small>Start one via MCP or CLI.</small></p>';
    } else {
      el.innerHTML = tasks.map(t => `
        <div class="task">
          <div class="task-header">
            <span class="task-topic">${esc(t.topic)}</span>
            <span class="task-id">${t.task_id.slice(0,16)}</span>
          </div>
          <div class="task-meta">
            <span><span class="indicator ${t.status}"></span> <span class="status-badge ${t.status}">${t.status}</span></span>
            <span>${t.stage || '—'}</span>
            <span>${Math.floor(t.progress*100)}%</span>
            <span>${formatElapsedMinutes(t.elapsed)}</span>
          </div>
          <div class="progress-bar">
            <div class="progress-fill ${t.status}" style="width:${Math.max(t.progress*100,1)}%"></div>
          </div>
          ${t.status==='completed' && t.has_report
            ? `<span class="report-link" onclick="viewReport('${t.task_id}')">View report (${(t.char_count/1000).toFixed(1)}K chars)</span>`+
              (t.has_pdf ? ` <span class="report-link" style="color:#d29922" onclick="window.open('/download/${encodeURIComponent(t.pdf_filename)}')">⬇ PDF</span>` : '')
            : ''}
        </div>
      `).join('');
    }
    document.getElementById('last-update').textContent = 'Last updated: '+new Date().toLocaleTimeString();
  } catch(e) {
    fetchErrorCount++;
    if(fetchErrorCount > 2) {
      document.getElementById('tasks').innerHTML = '<p class="error-msg">Cannot reach server — check if container is running.</p>';
    }
  }
}
function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
async function startResearch() {
  const topic = document.getElementById('topic').value.trim();
  const depth = document.getElementById('depth').value;
  const pdf = document.getElementById('pdf').checked;
  const btn = document.getElementById('start-btn');
  const fb = document.getElementById('feedback');
  if(!topic) { fb.className='feedback error'; fb.textContent='Please enter a topic.'; return; }
  btn.disabled = true; fb.className='feedback'; fb.textContent='Starting…';
  try {
    const reqId = Date.now();
    const resp = await fetch('/mcp',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({jsonrpc:'2.0',id:reqId,method:'tools/call',params:{name:'deep_research',arguments:{topic,depth,pdf,max_iterations:2}}})});
    const data = await resp.json();
    const text = data.result?.content?.[0]?.text || '';
    const match = text.match(/research-[a-f0-9]{8,}/);
    const taskId = match ? match[0] : null;
    if(taskId) {
      fb.className='feedback success';
      fb.innerHTML = 'Started <code>'+esc(taskId.slice(0,16))+'</code> — refreshing in 2s';
      document.getElementById('topic').value = '';
      document.getElementById('pdf').checked = false;
      setTimeout(refresh, 2000);
    } else {
      fb.className='feedback error'; fb.textContent='Failed: no task ID in response';
    }
  } catch(e) {
    fb.className='feedback error'; fb.textContent='Failed to start: '+e.message;
  } finally {
    btn.disabled = false;
  }
}
async function viewReport(taskId) {
  const overlay = document.getElementById('modal-overlay');
  const body = document.getElementById('modal-body');
  const title = document.getElementById('modal-title');
  overlay.classList.add('active');
  body.innerHTML = '<p class="modal-loading">Loading report…</p>';
  title.textContent = 'Report • '+taskId.slice(0,16);
  try {
    const resp = await fetch('/mcp',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({jsonrpc:'2.0',id:Date.now(),method:'tools/call',params:{name:'research_status',arguments:{task_id:taskId}}})});
    const data = await resp.json();
    const text = data.result?.content?.[0]?.text || 'Report not found';
    body.innerHTML = '<pre>'+esc(text)+'</pre>';
  } catch(e) {
    body.innerHTML = '<p class="error-msg">Failed to load report: '+esc(e.message)+'</p>';
  }
}
function closeModal() {
  document.getElementById('modal-overlay').classList.remove('active');
}
refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>'''
        return HTMLResponse(html)

    async def download_file(request):
        if not _dashboard_access_allowed(request):
            return _dashboard_forbidden()

        import urllib.parse

        filename = request.path_params.get('filename', '')
        filename = urllib.parse.unquote(filename)
        report_dir = _get_report_dir().resolve()
        filepath = (report_dir / filename).resolve()
        if not str(filepath).startswith(str(report_dir) + os.sep):
            return JSONResponse({'error': 'Forbidden'}, status_code=403)
        if not filepath.exists() or not filepath.is_file():
            return JSONResponse({'error': 'File not found'}, status_code=404)
        if filepath.suffix not in ('.md', '.pdf'):
            return JSONResponse({'error': 'File type not allowed'}, status_code=403)
        return FileResponse(filepath, filename=filename)

    routes = [
        Route('/', endpoint=dashboard, methods=['GET']),
        Route('/tasks', endpoint=tasks_api, methods=['GET']),
        Route('/health', endpoint=health_check),
        Route('/ready', endpoint=ready_check),
        Route('/mcp', endpoint=handle_sse, methods=['GET']),
        Route('/mcp', endpoint=mcp_probe, methods=['POST', 'OPTIONS']),
        Route('/stream/{task_id}', endpoint=handle_stream, methods=['GET']),
        Route('/download/{filename:path}', endpoint=download_file, methods=['GET']),
    ]
    if sse is not None:
        routes.append(Mount('/messages/', app=sse.handle_post_message))
    return Starlette(routes=routes)


async def _run_sse(host: str = '0.0.0.0', port: int = 8100):
    """Run with SSE/HTTP transport (for Docker deployment)."""
    global _main_event_loop
    _main_event_loop = asyncio.get_running_loop()

    from mcp.server.sse import SseServerTransport
    import uvicorn

    sse = SseServerTransport('/messages/')
    app = create_http_app(sse=sse)

    logger.info('MCP SSE server listening on %s:%d', host, port)
    config = uvicorn.Config(app, host=host, port=port, log_level='info')
    server_uv = uvicorn.Server(config)
    await server_uv.serve()

def main():
    parser = argparse.ArgumentParser(
        description="Deep Research MCP Server — expose research as an MCP tool"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8100,
        help="Port for SSE transport (default: 8100)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host for SSE transport (default: 0.0.0.0)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Validate config at startup
    from app.config import config as app_config
    issues = app_config.validate()
    for issue in issues:
        logging.warning("Config: %s", issue)
    critical = [i for i in issues if "WORKER_API_KEY" in i or "WORKER_API_BASE" in i]
    if critical:
        logging.error("Cannot start: missing required configuration")
        sys.exit(1)

    if args.transport == "stdio":
        asyncio.run(_run_stdio())
    else:
        asyncio.run(_run_sse(host=args.host, port=args.port))


if __name__ == "__main__":
    main()
