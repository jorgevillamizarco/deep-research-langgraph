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

The agent will:
1. Generate a structured research plan with 5 goals
2. Execute parallel web searches via SearXNG/Google
3. Synthesize findings into a comprehensive report
4. Quality-check results with an iterative critique loop
5. Return a fully cited markdown report

Use this for: competitive analysis, market research, technical deep-dives,
regulatory landscape reviews, vendor ecosystem mapping, and literature surveys.
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "The research topic — be specific. Include context, constraints, and any reference data.",
                    },
                    "max_iterations": {
                        "type": "integer",
                        "description": "Max critique-refinement loops (default: 3). Higher = better quality but slower.",
                        "default": 3,
                    },
                },
                "required": ["topic"],
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


async def _handle_deep_research(
    arguments: dict[str, Any] | None
) -> list[types.TextContent | types.EmbeddedResource]:
    """Run the full LangGraph research pipeline."""

    topic = (arguments or {}).get("topic", "")
    max_iterations = (arguments or {}).get("max_iterations", 3)

    if not topic:
        return [types.TextContent(type="text", text="Error: 'topic' is required.")]

    # Import here so the module can be imported without all deps
    from app.agent import build_research_graph
    from app.config import config as research_config

    # Override max iterations from the tool call
    os.environ["MAX_SEARCH_ITERATIONS"] = str(max_iterations)

    graph = build_research_graph()

    initial_state = {
        "topic": topic,
        "plan_approved": True,  # Skip interrupt in MCP mode
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
        "max_iterations": max_iterations,
        "url_to_short_id": {},
        "sources": {},
        "final_cited_report": None,
        "final_report_with_citations": None,
        "messages": [],
        "errors": [],
        "evaluation_scores": [],
        "total_tokens": 0,
        "cached_goal_count": 0,
    }

    import time

    thread_id = f"research-{int(time.time())}"
    thread_config = {"configurable": {"thread_id": thread_id}}

    # Notify progress
    await server.request_context.session.send_progress_notification(
        progress_token="research",
        progress=0.1,
        total=1.0,
    )

    try:
        # Generate plan first (avoids double-entry from stream+resume)
        from app.nodes.planner import generate_plan_only

        plan_result = generate_plan_only(topic)
        initial_state["research_plan"] = plan_result["research_plan"]
        initial_state["report_sections"] = plan_result["report_sections"]
        initial_state["parallel_goals"] = plan_result["parallel_goals"]
        initial_state["plan_approved"] = True
        if plan_result.get("total_tokens"):
            initial_state["total_tokens"] = plan_result["total_tokens"]

        # Run graph with approved plan (single invoke, no interrupt)
        final_values = graph.invoke(initial_state, thread_config)

        report = (
            final_values.get("final_report_with_citations")
            or final_values.get("final_cited_report")
            or ""
        )

        await server.request_context.session.send_progress_notification(
            progress_token="research",
            progress=1.0,
            total=1.0,
        )

        if not report:
            errors = final_values.get("errors", [])
            err_text = "\n".join(errors) if errors else "Unknown error"
            return [
                types.TextContent(
                    type="text",
                    text=f"## Research Failed\n\nNo report was generated.\n\n**Errors:**\n{err_text}",
                )
            ]

        # Save report with timestamp
        report_dir = Path(os.getenv("RESEARCH_OUTPUT_DIR", os.path.expanduser("~/research")))
        report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_topic = topic.replace(" ", "_").replace("/", "_")[:40]
        filename = report_dir / f"report_{safe_topic}_{timestamp}.md"

        with open(filename, "w") as f:
            f.write(report)

        # Generate PDF
        try:
            from app.cli import _convert_to_pdf
            pdf_path = _convert_to_pdf(filename)
        except Exception:
            pdf_path = None

        pdf_note = f"\n**PDF:** {pdf_path}" if pdf_path else ""

        return [
            types.TextContent(
                type="text",
                text=f"""## Research Complete

**Topic:** {topic}
**Report saved:** {filename}{pdf_note}
**Report size:** {len(report):,} chars

---

{report[:8000]}""",
            ),
            types.EmbeddedResource(
                type="resource",
                resource=types.TextResourceContents(
                    uri=f"file://{filename}",
                    mimeType="text/markdown",
                    text=report,
                ),
            ),
        ]

    except Exception as e:
        logger.exception("Research failed")
        return [
            types.TextContent(
                type="text", text=f"## Research Failed\n\n**Error:** {e}"
            )
        ]


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
                            "description": "Run a deep, multi-phase research investigation on any topic. Generates plan, does web research, quality-checks, and returns a fully cited markdown report.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "topic": {"type": "string", "description": "The research topic"},
                                    "max_iterations": {"type": "integer", "description": "Max critique-refinement loops (default: 3)", "default": 3},
                                },
                                "required": ["topic"],
                            },
                        },
                    ]
                },
            })
        elif method == "tools/call":
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": "For full tool execution, connect via SSE at GET /mcp"}],
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

    app = Starlette(
        routes=[
            Route("/health", endpoint=health_check),
            Route("/mcp", endpoint=handle_sse, methods=["GET"]),
            Route("/mcp", endpoint=mcp_probe, methods=["POST", "OPTIONS"]),
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
