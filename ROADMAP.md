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
- [x] MCP server (SSE + JSON-RPC POST handler — tools/call executes directly, no stub redirect)
- [x] MCP POST transport fixes (send_progress_notification degrades silently, AnyUrl → str serialization)
- [x] Async execution (deep_research returns task_id immediately, background thread, research_status polling, task disk persistence)
- [x] Stronger critic model (defaults to v4-pro, warns if critic == worker)
- [x] URL content fetching (fetch top 3 search results for full-page text)
- [x] Output tiering (depth: brief/standard)
- [x] Docker host mount for reports (reports on host filesystem, not Docker volume)
- [x] Live progress tracking (graph.stream() maps per-node progress: 20%→30%→45%→55%→65%→85%→95%)
- [x] Comprehensive docs (ARCHITECTURE.md, AGENTS.md, skills)
- [ ] Self-documenting MCP tools (~~outputSchema~~ — reverted: Hermes enforces it on results, tools return markdown text not JSON)

## Next — Polish

### Better model defaults

Both worker and critic default to DeepSeek V4 Flash. Stronger critic would catch more subtle issues.

✅ Done: documented in `.docker.env.template` with recommendation to use stronger CRITIC_MODEL.

### Streaming report output

Progress markers show milestones but user can't watch the report form.

✅ Done: composer now streams report to stdout token-by-token via `llm.stream()` with `flush=True`.

## Later — Big Features

### Cross-run memory

✅ Implemented. Goal-level cache with key phrase hashing, fuzzy matching, delta validation, opt-in only.

**Lesson:** Cross-run caching has diminishing returns for single-agent research tools. Hit rate is fundamentally limited by LLM non-determinism — the planner generates different goal wordings each run. Semantic chunking + vector retrieval would add significant complexity for marginal benefit. Keep as lightweight opt-in bonus, not a core feature.

**Design:**
- `--cache` flag required (never enabled by default)
- Cache key: SHA256 of normalized goal text
- TTL by source tier: 2 weeks (T1), 1 week (T2), 2 days (T3)
- Date-bound topics (contain year) never cached
- Delta check runs 1 lightweight search before serving
- Transparent: Methodology section notes cached goals
- Cache file: `research_cache.db` alongside checkpoints

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
