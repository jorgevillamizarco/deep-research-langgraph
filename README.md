# Deep Research Agent (LangGraph)

A production-ready deep research agent built with **LangGraph** that performs multi-phase research: collaborative planning, parallel web research, iterative refinement with critique loop, and final report synthesis with structured citations.

Replicates the architecture of Google's [ADK deep-search sample](https://github.com/google/adk-samples/tree/main/python/agents/deep-search) using LangGraph's StateGraph, subgraphs, interrupts, and conditional routing.

## Architecture

```
planner (plan_generator + section_planner + interrupt)
  │
  ▼
researcher (section_researcher: two-phase execution [RESEARCH] → [DELIVERABLE])
  │
  ▼
[refinement_subgraph]  ◄──────────────────────┐
  │  evaluator (research_evaluator)            │
  │    ├─ pass ──► exit subgraph               │
  │    └─ fail ──► enhancer ───────────────────┘ (loop, iteration++)
  │
  ▼
composer (report_composer + citation replacement)
```

## Quick Start

```bash
# Install
cd deep-research-langgraph
python3 -m venv .venv
.venv/bin/pip install -e .

# Run research
.venv/bin/python -m app.cli "Your research topic"

# With auto-approve (skip plan interrupt):
.venv/bin/python -m app.cli --auto "Your research topic"
```

## Configuration

Set via environment variables (or `.env` file):

|| Variable | Default | Description |
|----------|---------|-------------|
| `WORKER_MODEL` | `deepseek-v4-flash` | Model for research/composition tasks |
| `CRITIC_MODEL` | `deepseek-v4-pro` | Model for evaluation (should be stronger) |
| `WORKER_API_KEY` | `OPENAI_API_KEY` | API key for worker model |
| `WORKER_API_BASE` | `OPENAI_API_BASE` | API base URL for worker |
| `CRITIC_API_KEY` | falls back to WORKER | API key for critic model |
| `CRITIC_API_BASE` | falls back to WORKER | API base for critic model |
| `SEARXNG_URL` | `http://deep-research-searxng:8080` | Internal SearXNG endpoint |
| `MAX_SEARCH_ITERATIONS` | `3` | Max critique loop iterations |
| `RESEARCH_OUTPUT_DIR` | `/data` | Report output directory (Docker mount) |
| `CHECKPOINT_DB_PATH` | `checkpoints.db` | SQLite checkpoint DB path |
| `TAVILY_API_KEY` | (none → SearXNG → DuckDuckGo) | Web search API key |

## Project Structure

```
deep-research-langgraph/
├── app/
│   ├── agent.py          # StateGraph + subgraph + compilation
│   ├── state.py          # ResearchState TypedDict + Pydantic models
│   ├── config.py         # ResearchConfig dataclass
│   ├── cli.py            # CLI entry point
│   ├── nodes/
│   │   ├── planner.py    # Plan generation + section outline
│   │   ├── researcher.py # Two-phase web research
│   │   ├── evaluator.py  # Quality critique (Feedback schema)
│   │   ├── enhancer.py   # Follow-up search execution
│   │   └── composer.py   # Report synthesis + citations
│   └── tools/
│       ├── search.py     # Tavily/DuckDuckGo wrapper
│       └── citations.py  # Source extraction + tag replacement
├── tests/
│   └── test_agent.py     # Unit tests
└── pyproject.toml
```

## Key Design Decisions

- **StateGraph** over Functional API — needed for conditional routing (pass/fail from evaluator)
- **Subgraph for refinement loop** — isolates critic→enhancer logic, mirrors ADK's LoopAgent
- **JSON prompting for evaluator** instead of `with_structured_output` — broader model compatibility
- **Two-pass plan approval** (outside graph) instead of interrupt() — avoids double-entry bug, saves one LLM call
- **State reducers** — `operator.or_` merges sources across refinement iterations

## Development

```bash
# Tests
.venv/bin/python -m pytest tests/ -v

# Smoke test (requires API key)
.venv/bin/python smoke_test.py
```
