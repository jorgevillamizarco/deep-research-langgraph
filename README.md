# Deep Research Agent (LangGraph)

A LangGraph-based deep research agent with:
- two-phase execution (`[RESEARCH]` → `[DELIVERABLE]`)
- parallel fan-out via Send API
- iterative refinement with evaluator + enhancer loop
- MCP server + web dashboard
- cited markdown/PDF output
- checkpoint persistence across deploys

## Architecture

```
planner
  │
  ├─► parallel_researcher(goal 1)
  ├─► parallel_researcher(goal 2)
  └─► parallel_researcher(goal N)
  │
  ▼
merge_findings
  │
  ▼
refinement_subgraph
  deliverable → evaluator → enhancer → deliverable
  │
  ▼
composer
```

## Quick Start

### Local

```bash
cd deep-research-langgraph
python3 -m venv .venv
.venv/bin/python -m pip install -e . pytest

export WORKER_API_KEY=...
export WORKER_API_BASE=https://api.deepseek.com
# optional but recommended
export CRITIC_MODEL=deepseek-v4-pro

.venv/bin/python -m app.cli --help
.venv/bin/python -m app.cli --auto "Your research topic"
```

### Docker

```bash
cp .docker.env.template .docker.env
# fill in API keys

./deploy.sh start  # rebuilds the current image and restarts the stack
curl -s http://localhost:8100/health
curl -s http://localhost:8100/ready
```

### Docker Compose

```bash
cp .docker.env.template .docker.env
# fill in API keys

docker-compose up -d
curl -s http://localhost:8100/health
curl -s http://localhost:8100/ready
```

## Configuration

This project does **not** auto-load a generic `.env` file for local CLI runs.
Use exported environment variables locally, or `.docker.env` / `.docker.env.template` for Docker.

| Variable | Default | Description |
|---|---|---|
| `WORKER_MODEL` | `deepseek-v4-flash` | Research/composition model |
| `CRITIC_MODEL` | `deepseek-v4-pro` | Evaluation model |
| `WORKER_API_KEY` | `OPENAI_API_KEY` fallback | API key for worker model |
| `WORKER_API_BASE` | `OPENAI_API_BASE` fallback | API base URL |
| `CRITIC_API_KEY` | falls back to worker | Critic API key |
| `CRITIC_API_BASE` | falls back to worker | Critic API base |
| `SEARXNG_URL` | `http://deep-research-searxng:8080` | Search backend URL |
| `MAX_SEARCH_ITERATIONS` | `3` | Max critique loops |
| `RESEARCH_OUTPUT_DIR` | `/data` in Docker | Report output directory |
| `CHECKPOINT_DB_PATH` | `checkpoints.db` | SQLite checkpoint DB path |
| `DASHBOARD_PUBLIC` | unset | Set to `1`/`true` to expose dashboard/task/download routes beyond local/private-network clients |
| `TAVILY_API_KEY` | optional | Enables Tavily as primary search backend |
| `FALLBACK_API_KEY` | optional | Fallback LLM provider key |
| `FALLBACK_API_BASE` | optional | Fallback LLM provider base |

## Runtime Endpoints

| Endpoint | Purpose |
|---|---|
| `/` | Dashboard (local/private-network only by default; set `DASHBOARD_PUBLIC=1` to expose remotely) |
| `/health` | Cheap liveness check |
| `/ready` | Deep readiness check: config, writable output/checkpoint paths, authenticated LLM endpoint reachability, active search backend probe |
| `/mcp` | MCP endpoint (GET SSE, POST JSON-RPC) |
| `/stream/{task_id}` | SSE progress stream (local/private-network only by default) |
| `/tasks` | Dashboard/API task list (sanitized filenames, no absolute paths; local/private-network only by default) |
| `/download/{filename}` | Download `.md` / `.pdf` reports (local/private-network only by default) |

## Search Behavior

Backend priority:
1. Tavily
2. SearXNG
3. DDGS fallback

Language handling:
- planner annotates jurisdiction-specific goals with `(search in LANGUAGE; ...)`
- researcher passes the language hint to search
- SearXNG uses the requested language instead of forcing English
- Tavily routes non-English searches through SearXNG when available
- DDGS fallback maps language hints to locale-specific regions (for example `es-es`, `de-de`)
- query-language inference still falls back to English when no hint exists

## Project Structure

```text
deep-research-langgraph/
├── app/
│   ├── agent.py
│   ├── cli.py
│   ├── config.py
│   ├── mcp_server.py
│   ├── state.py
│   ├── tokens.py
│   ├── nodes/
│   └── tools/
├── tests/
│   ├── test_agent.py
│   ├── test_integration.py
│   └── test_mcp_server.py
├── .github/workflows/ci.yml
├── docker-compose.yml
├── deploy.sh
└── pyproject.toml
```

## Development

```bash
# test suite
.venv/bin/python -m pytest tests/ -q

# CLI help should work without API config
.venv/bin/python -m app.cli --help

# local health checks after starting server
curl -s http://localhost:8100/health
curl -s http://localhost:8100/ready

# MCP initialize smoke test
curl -s -X POST http://localhost:8100/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'
```

Current test count: **45 passing tests**.
