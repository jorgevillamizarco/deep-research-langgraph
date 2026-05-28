# Roadmap

## Now — Production Ready

- [x] Two-phase execution (RESEARCH → DELIVERABLE) with Send API fan-out
- [x] Critique loop with numeric rubric evaluator
- [x] Circuit breaker (score stagnation detection)
- [x] State pruning (O(N²) checkpoint bloat prevention)
- [x] SQLite checkpointing (survives restarts)
- [x] Graceful save failure (report prints to stdout)
- [x] Error surface in final reports
- [x] Progress markers (real-time CLI feedback)
- [x] DELIVERABLE goal guarantee (3-layer: prompt + post-processing + regex failsafe)
- [x] PDF generation (pandoc + weasyprint)
- [x] Flexible report structure (planner sections as template)
- [x] Multi-model support (separate worker/critic via env vars)
- [x] Token tracking infrastructure (state field + shared get_llm)
- [x] Token tracking wired (all nodes report tokens via _TrackedChatOpenAI wrapper)
- [x] Planner double-entry fixed (two-pass: generate plan separately, graph runs once)
- [x] MCP server (SSE + JSON-RPC POST handler)
- [x] Docker deployment (agent + SearXNG, one-command deploy)
- [x] Comprehensive docs (ARCHITECTURE.md, AGENTS.md, skills)

## Next — Polish

### Better model defaults

Both worker and critic default to DeepSeek V4 Flash. Stronger critic would catch more subtle issues.

✅ Done: documented in `.docker.env.template` with recommendation to use stronger CRITIC_MODEL.

### Streaming report output

Progress markers show milestones but user can't watch the report form.

✅ Done: composer now streams report to stdout token-by-token via `llm.stream()` with `flush=True`.

## Later — Big Features

### Cross-run memory

Goal-level cache in SQLite to avoid re-researching the same goals across runs.

**Design:**

```
Cache lookup per RESEARCH goal:
  1. Hash goal text
  2. If topic contains \d{4}: skip (date-bound research, never cache)
  3. If --fresh flag: skip
  4. Look up by goal_hash in SQLite
  5. If not found → research fresh, cache
  6. If found but expired (TTL based on avg_source_tier) → research fresh
  7. If found and fresh → run 1 delta search for "topic + latest"
  8. If delta shows substantially new results → research fresh
  9. If delta clean → return cached findings
```

**Cache entry:** `{goal_hash, findings, sources, researched_at, avg_source_tier, youngest_source_date}`

**TTL by source tier:**
| Avg tier | TTL |
|----------|-----|
| ≤1.5 (mostly academic/official) | 6 months |
| 1.5-2.5 (mixed) | 3 months |
| >2.5 (mostly community/news) | 1 month |

**Not building (yet):**
- Semantic similarity matching (fuzzy, v2)
- Source-level cache (per-URL staleness is complex)
- Auto-invalidation (no heuristic beats `--fresh`)

### Streaming report generation

Composer generates report section by section, streaming output to CLI in real-time. User watches the report form instead of staring at a blank terminal for 3 minutes.

### Research topic suggestions

Agent analyzes previous research topics, identifies gaps, suggests follow-up topics. Builds a research program instead of one-off queries.

### Multi-agent collaboration

Multiple research agents collaborating on a large topic. Planner distributes subtopics, agents research independently, synthesizer merges findings. Like MapReduce for research.

### Browser-based research

Current agent uses web search + text extraction. Adding browser-based research (navigate pages, click through, extract structured data) would improve depth for topics requiring interactive exploration.

## Skills Captured

| Skill | Content |
|-------|---------|
| `langgraph-agent-patterns` | StateGraph, Send API, subgraphs, interrupt/resume, checkpointing, JSON prompting, DELIVERABLE guarantee, circuit breaker, state pruning, progress markers, token tracking |
| `langgraph-agent-deployment/references/architecture-patterns.md` | Two-phase execution, refinement subgraph, Send API fan-out, circuit breaker, state pruning, progress markers, token tracking, auto-approve pattern |
| `langgraph-agent-deployment/references/quality-patterns.md` | Numeric rubric, per-claim confidence, source tiers, contradiction detection, DELIVERABLE guarantee, error surface |
| `langgraph-agent-deployment/references/pdf-generation.md` | Pandoc+weasyprint primary, Python fallback, Docker setup |
| `multi-agent-orchestration/references/langgraph-pipeline-patterns.md` | Send API, subgraphs, iteration loops, circuit breaker, interrupt/resume, JSON prompting |
