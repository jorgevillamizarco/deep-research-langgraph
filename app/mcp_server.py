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
_TASK_TTL_SECONDS = 86400  # 24 hours — tasks survive between sessions

# ── SSE streaming: task_id → asyncio.Queue of progress events
_stream_queues: dict[str, asyncio.Queue[dict[str, Any]]] = {}
_stream_lock = asyncio.Lock()


def _get_report_dir() -> Path:
    """Return the first writable report directory from the fallback chain.

    Order: RESEARCH_OUTPUT_DIR env → ~/research → current directory.
    """
    candidates = [
        Path(os.getenv("RESEARCH_OUTPUT_DIR", "")),
        Path.home() / "research",
        Path.cwd(),
    ]
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
    """Quick web search via SearXNG."""
    query = (arguments or {}).get("query", "")
    max_results = min(int((arguments or {}).get("max_results", 5)), 15)

    if not query:
        return [types.TextContent(type="text", text="Error: 'query' is required.")]

    import httpx

    searxng_url = os.getenv("SEARXNG_URL", "http://localhost:8080")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{searxng_url.rstrip('/')}/search",
                params={"q": query, "format": "json", "language": "en"},
                headers={"User-Agent": "DeepResearch-MCP/1.0"},
            )
            resp.raise_for_status()
            data = resp.json()

    except Exception as e:
        return [
            types.TextContent(
                type="text",
                text=f"Search failed: {e}\n\nTry using DuckDuckGo directly or check if SearXNG is running on {searxng_url}.",
            )
        ]

    results = data.get("results", [])[:max_results]

    if not results:
        return [types.TextContent(type="text", text=f"No results found for: {query}")]

    lines = [f"# Search Results: {query}", ""]
    for i, r in enumerate(results, 1):
        title = r.get("title", "Untitled")
        url = r.get("url", "")
        snippet = r.get("content", r.get("snippet", ""))
        engine = r.get("engine", "")
        lines.append(f"## {i}. [{title}]({url})")
        if snippet:
            lines.append(f"   {snippet[:500]}")
        lines.append("")

    return [types.TextContent(type="text", text="\n".join(lines))]


def _push_stream_event(task_id: str, event: dict[str, Any]) -> None:
    """Push a progress event to the SSE stream queue for a task (thread-safe)."""
    loop = asyncio.get_event_loop()
    if task_id in _stream_queues:
        # Use call_soon_threadsafe to push from background thread
        q = _stream_queues[task_id]
        loop.call_soon_threadsafe(q.put_nowait, event)


def _deep_research_runner(task_id: str, topic: str, max_iterations: int, depth: str = "standard"):
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

    try:
        os.environ["MAX_SEARCH_ITERATIONS"] = str(max_iterations)
        graph = build_research_graph()
        initial_state = {
            "topic": topic, "plan_approved": True, "user_feedback": None,
            "research_plan": None, "report_sections": None,
            "section_research_findings": None, "research_evaluation": None,
            "current_goal": "", "parallel_goals": [], "parallel_findings": [],
            "research_iteration": 0, "iteration_count": 0,
            "max_iterations": max_iterations,
            "url_to_short_id": {}, "sources": {},
            "final_cited_report": None, "final_report_with_citations": None,
            "messages": [], "errors": [], "evaluation_scores": [],
            "total_tokens": 0, "cached_goal_count": 0,
            "depth": depth,
        }
        thread_id = f"research-{int(time.time())}"
        thread_config = {"configurable": {"thread_id": thread_id}}

        # Generate plan
        plan_result = generate_plan_only(topic)
        initial_state["research_plan"] = plan_result["research_plan"]
        initial_state["report_sections"] = plan_result["report_sections"]
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
            "__end__": 1.0,
        }

        report = ""
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

        if not report:
            err_text = "No report was generated. Check logs for details."
            _update(task_id, status="failed", error=err_text, progress=1.0, stage="error")
            return

        # Save report
        report_dir = Path(os.getenv("RESEARCH_OUTPUT_DIR", os.path.expanduser("~/research")))
        report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_topic = topic.replace(" ", "_").replace("/", "_")[:40]
        filename = report_dir / f"report_{safe_topic}_{timestamp}.md"
        with open(filename, "w") as f:
            f.write(report)

        _update(task_id, progress=0.95, stage="saving")

        if task:
            task["status"] = "completed"
            task["progress"] = 1.0
            task["report"] = report
            task["report_path"] = str(filename)
            task["char_count"] = len(report)
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


async def _handle_deep_research(
    arguments: dict[str, Any] | None
) -> list[types.TextContent]:
    """Start deep research in background, return task_id immediately."""
    import time, uuid

    topic = (arguments or {}).get("topic", "")
    max_iterations = max(1, min(int((arguments or {}).get("max_iterations", 2)), 10))
    depth = (arguments or {}).get("depth", "standard")

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
        }

    # Cleanup stale tasks (>1 hour old)
    async with _research_lock:
        stale = [tid for tid, t in _research_tasks.items()
                 if now - t.get("created_at", now) > _TASK_TTL_SECONDS]
        for tid in stale:
            del _research_tasks[tid]

    # Launch background task in thread (sync graph.invoke blocks asyncio event loop)
    asyncio.create_task(asyncio.to_thread(_deep_research_runner, task_id, topic, max_iterations, depth))

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
        return [types.TextContent(
            type="text",
            text=f"""## Research In Progress

**Task ID:** {task_id}
**Topic:** {task.get("topic", "")}
**Status:** {status}
**Progress:** {task.get("progress", 0):.0%}
**Elapsed:** {elapsed:.0f}s

Poll again in 10-15 seconds."""
        )]

    elif status == "completed":
        report = task.get("report", "")
        return [types.TextContent(
            type="text",
            text=f"""## Research Complete

**Task ID:** {task_id}
**Topic:** {task.get("topic", "")}
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


async def _run_sse(host: str = "0.0.0.0", port: int = 8100):
    """Run with SSE/HTTP transport (for Docker deployment)."""
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.responses import Response, JSONResponse
    from starlette.routing import Mount, Route
    import uvicorn

    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(
                streams[0],
                streams[1],
                InitializationOptions(
                    server_name="deep-research",
                    server_version="0.1.0",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
        return Response()

    async def health_check(request):
        return JSONResponse({"status": "ok", "server": "deep-research"})

    async def mcp_probe(request):
        """Handle MCP JSON-RPC over POST (Hermes' default transport).

        Hermes probes by sending an initialize request via POST.
        If the server responds correctly, Hermes continues with tools/list
        over POST instead of establishing an SSE stream.
        """
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})

        method = body.get("method", "")
        request_id = body.get("id", 0)

        if method == "initialize":
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "deep-research", "version": "0.1.0"},
                    "capabilities": {"tools": {}, "resources": {}},
                },
            })
        elif method == "tools/list":
            # Return actual tools (ADK-aligned)
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": "search",
                            "description": "Quick web search via SearXNG (Google/Bing/DuckDuckGo aggregated). Returns title, URL, and snippet.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string", "description": "The search query"},
                                    "max_results": {"type": "integer", "description": "Max results (default: 5, max: 15)", "default": 5},
                                },
                                "required": ["query"],
                            },
                        },
                        {
                            "name": "deep_research",
                            "description": "Run a deep, multi-phase research investigation on any topic. Returns a task_id immediately — poll with research_status(task_id) for results.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "topic": {"type": "string", "description": "The research topic"},
                                    "max_iterations": {"type": "integer", "description": "Max critique-refinement loops (default: 2)", "default": 2},
                                    "depth": {"type": "string", "description": "Report depth: brief or standard", "default": "standard"},
                                },
                                "required": ["topic"],
                            },
                        },
                        {
                            "name": "research_status",
                            "description": "Check the status of a deep_research task. Returns 'running'/'completed'/'failed' with progress, report, or error.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "task_id": {"type": "string", "description": "Task ID from deep_research"},
                                },
                                "required": ["task_id"],
                            },
                        },
                    ]
                },
            })
        elif method == "tools/call":
            # Execute tool via POST (same handler as SSE)
            tool_name = body.get("params", {}).get("name", "")
            tool_args = body.get("params", {}).get("arguments", {})
            try:
                result = await handle_call_tool(tool_name, tool_args)
                # Extract text from MCP types for JSON response
                content = []
                for item in result:
                    if isinstance(item, types.TextContent):
                        content.append({"type": "text", "text": item.text})
                    elif isinstance(item, types.EmbeddedResource):
                        content.append({"type": "resource", "resource": {
                            "uri": str(item.resource.uri) if hasattr(item.resource, 'uri') else "",
                            "mimeType": item.resource.mimeType if hasattr(item.resource, 'mimeType') else "text/markdown",
                        }})
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"content": content, "isError": False},
                })
            except Exception as e:
                logger.exception("tools/call failed via POST")
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Tool execution failed: {e}"}],
                        "isError": True,
                    },
                })
        elif method == "notifications/initialized":
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": {}})
        else:
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            })

    async def handle_stream(request):
        """SSE endpoint for streaming real-time research progress.

        Connect to /stream/{task_id} after calling deep_research to receive
        live progress events. Events include:

        - event: started — research has begun
        - event: update — progress/stage changed (e.g. "parallel_researcher", "composer")
        - event: completed — research done, report_path included
        - event: failed — error occurred
        - event: heartbeat — sent every 5s to keep connection alive

        Returns 404 if task_id not found.
        """
        task_id = request.path_params.get("task_id", "")
        if not task_id:
            return JSONResponse({"error": "task_id required"}, status_code=400)

        # Check task exists
        task = _research_tasks.get(task_id)
        if not task:
            task = await asyncio.to_thread(_load_persisted_task, task_id)
        if not task:
            return JSONResponse({"error": "Task not found"}, status_code=404)

        # Create a queue for this stream
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        async with _stream_lock:
            _stream_queues[task_id] = q

        # Capture task snapshot for the generator
        _task_snapshot = dict(task)  # type: ignore[arg-type]

        async def event_generator():
            import json as _json
            # Send initial state
            yield f"event: started\ndata: {_json.dumps({'task_id': task_id, 'topic': _task_snapshot.get('topic', ''), 'status': _task_snapshot.get('status', 'running'), 'progress': _task_snapshot.get('progress', 0)})}\n\n".encode("utf-8")

            last_progress = _task_snapshot.get("progress", 0)
            completed = False

            while not completed:
                try:
                    # Wait for next event with timeout
                    event = await asyncio.wait_for(q.get(), timeout=5.0)
                    yield f"event: {event.get('event', 'update')}\ndata: {_json.dumps(event)}\n\n".encode("utf-8")

                    if event.get("event") in ("completed", "failed"):
                        completed = True
                        break
                except asyncio.TimeoutError:
                    # Heartbeat to keep connection alive
                    # Check if task was completed in another way
                    current_task = _research_tasks.get(task_id)
                    if current_task:
                        current_progress = current_task.get("progress", last_progress)
                        if current_progress != last_progress:
                            last_progress = current_progress
                            yield f"event: heartbeat\ndata: {_json.dumps({'task_id': task_id, 'progress': current_progress, 'status': current_task.get('status', 'running')})}\n\n".encode("utf-8")
                        if current_task.get("status") in ("completed", "failed"):
                            yield f"event: {current_task['status']}\ndata: {_json.dumps({'task_id': task_id, 'status': current_task['status'], 'progress': 1.0})}\n\n".encode("utf-8")
                            completed = True
                    else:
                        # Task gone — send completion and close
                        yield f"event: completed\ndata: {_json.dumps({'task_id': task_id, 'status': 'completed', 'progress': 1.0})}\n\n".encode("utf-8")
                        completed = True

            # Cleanup queue
            async with _stream_lock:
                _stream_queues.pop(task_id, None)

        from starlette.responses import StreamingResponse
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )

    app = Starlette(
        routes=[
            Route("/health", endpoint=health_check),
            Route("/mcp", endpoint=handle_sse, methods=["GET"]),
            Route("/mcp", endpoint=mcp_probe, methods=["POST", "OPTIONS"]),
            Route("/stream/{task_id}", endpoint=handle_stream, methods=["GET"]),
            Mount("/messages/", app=sse.handle_post_message),
        ]
    )

    logger.info("MCP SSE server listening on %s:%d", host, port)
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
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

    if args.transport == "stdio":
        asyncio.run(_run_stdio())
    else:
        asyncio.run(_run_sse(host=args.host, port=args.port))


if __name__ == "__main__":
    main()
