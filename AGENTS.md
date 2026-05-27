# Deep Research Agent — Project Context

## Architecture

LangGraph StateGraph with 4 nodes + 1 subgraph (two-phase execution):

```
planner → researcher → [refinement subgraph] → composer → report
                              │
                    deliverable ─► evaluator ─┤─ pass ──→ exit
                                ▲              └─ fail ──→ enhancer ──┘
                                └─────────────────────────── loop ────┘
```

Parallel fan-out via Send API: planner extracts [RESEARCH] goals → N parallel_researcher nodes (Phase 1) → merge_findings → refinement_subgraph (Phase 2 + critique).

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
| `app/nodes/researcher.py` | Phase 1 research + Phase 2 deliverable synthesis |
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
| `RESEARCH_OUTPUT_DIR` | `~/research` | Report output directory |
| `CHECKPOINT_DB_PATH` | `checkpoints.db` | SQLite checkpoint DB path |

**Multi-model support:** Set `WORKER_MODEL` for research/composition tasks and `CRITIC_MODEL` for evaluation. Use a stronger model for the critic (e.g., Claude Sonnet, GPT-4) to catch subtle quality issues. DeepSeek V4 Flash is the default for both — fast and cost-effective for bulk research.

## MCP Tool: `deep_research`

```json
{
  "topic": "string (required)",
  "max_iterations": "integer (optional, default 3)"
}
```

Returns markdown report with citations, saved to `RESEARCH_OUTPUT_DIR`.

## Production Notes

- **State pruning:** Composer caps accumulator lists (messages: 20, errors: 50, evaluation_scores: 5, parallel_findings: 20) to prevent O(N²) checkpoint bloat (5.3 GB observed at 200 turns).
- **Checkpointing:** SQLite by default via `langgraph-checkpoint-sqlite`. Survives MCP server restarts.
- **Circuit breaker:** Evaluator loop detects score stagnation across 2 iterations — forces pass to avoid wasted cycles.

## Related Skills

Built with patterns now captured in reusable skills:

| Skill | What |
|-------|------|
| `langgraph-agent-patterns` | StateGraph construction, Send API, subgraphs, interrupt/resume, checkpointing, JSON prompting |
| `langgraph-agent-deployment` | MCP server, Docker, SearXNG, health checks, architecture patterns, quality patterns |
| `multi-agent-orchestration` | Send API fan-out, pipeline patterns, circuit breaker, human-in-the-loop |
