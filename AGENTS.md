# Deep Research Agent — Project Context

## Architecture

LangGraph StateGraph with 4 nodes + 1 subgraph:

```
planner → researcher → [refinement subgraph] → composer → report
                              │
                    evaluator ─┤─ pass ──→ exit
                               └─ fail ──→ enhancer → loop
```

**CLI:** `python -m app.cli --auto "topic"` (auto-approve plan)  
**MCP:** `python -m app.mcp_server --transport sse --port 8100`  
**Docker:** `docker compose up -d` (includes SearXNG)

## Key Files

| File | Purpose |
|------|---------|
| `app/agent.py` | StateGraph + subgraph + compilation |
| `app/cli.py` | Interactive CLI with plan review |
| `app/mcp_server.py` | MCP server exposing `deep_research` tool |
| `app/nodes/planner.py` | Plan generation + interrupt for human review |
| `app/nodes/researcher.py` | Two-phase web research + synthesis |
| `app/nodes/evaluator.py` | JSON-prompt quality evaluation |
| `app/nodes/enhancer.py` | Follow-up search on FAIL grade |
| `app/nodes/composer.py` | Report synthesis with `<cite>`→ markdown |
| `app/tools/search.py` | Tavily → SearXNG → DuckDuckGo fallback |
| `docker-compose.yml` | Agent + SearXNG deployment |

## Running

```bash
# CLI with plan review
python -m app.cli "Your research topic"

# CLI auto-mode (skip plan review)
python -m app.cli --auto "Your research topic"

# MCP stdio (for Hermes)
python -m app.mcp_server --transport stdio

# Docker + SearXNG
docker compose up -d
hermes mcp add research --url http://localhost:8100/mcp
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKER_MODEL` | `deepseek-v4-flash` | LLM for research tasks |
| `CRITIC_MODEL` | `deepseek-v4-flash` | LLM for evaluation |
| `WORKER_API_KEY` | — | API key for worker model |
| `WORKER_API_BASE` | — | API base URL |
| `SEARXNG_URL` | `http://localhost:8080` | Self-hosted search |
| `MAX_SEARCH_ITERATIONS` | `3` | Max critique loops |

## MCP Tool: `deep_research`

```json
{
  "topic": "string (required)",
  "max_iterations": "integer (optional, default 3)"
}
```

Returns markdown report with citations, saved to `RESEARCH_OUTPUT_DIR`.
