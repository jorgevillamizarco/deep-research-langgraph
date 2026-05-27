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
        )
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict[str, Any] | None
) -> list[types.TextContent | types.EmbeddedResource]:
    """Execute a research tool."""
    if name != "deep_research":
        raise ValueError(f"Unknown tool: {name}")

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
        "research_iteration": 0,
        "iteration_count": 0,
        "max_iterations": max_iterations,
        "url_to_short_id": {},
        "sources": {},
        "final_cited_report": None,
        "final_report_with_citations": None,
        "messages": [],
        "errors": [],
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
        for event in graph.stream(initial_state, thread_config):
            if isinstance(event, dict) and "__interrupt__" in event:
                # Auto-resume (plan already approved)
                from langgraph.types import Command

                final_values = graph.invoke(
                    Command(resume={"plan_approved": True}), thread_config
                )
                break

        else:
            # No interrupt — graph completed normally
            final_state = graph.get_state(thread_config)
            final_values = final_state.values

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

        return [
            types.TextContent(
                type="text",
                text=f"""## Research Complete

**Topic:** {topic}
**Report saved:** {filename}
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
    from starlette.responses import Response
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

    app = Starlette(
        routes=[
            Route("/mcp", endpoint=handle_sse, methods=["GET"]),
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
