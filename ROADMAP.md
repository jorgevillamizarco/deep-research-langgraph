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
- [x] Parallel citation extraction in merge_findings_node (fixes missing sources in parallel mode)
- [x] Writable directory fallback chain (RESEARCH_OUTPUT_DIR → ~/research → cwd)
- [x] LLM timeout/retry (timeout=60s, max_retries=2)
- [x] WeasyPrint CSS warning suppression
- [ ] Self-documenting MCP tools (~~outputSchema~~ — reverted: Hermes enforces it on results, tools return markdown text not JSON)

## Technical Debt & Known Issues

Architectural concerns from code review (May 2026). Not blockers — the agent is production-usable — but areas for improvement.

### 1. Test Coverage vs Complexity

12 unit tests for ~3,500 lines. Most mock the LLM and test isolated functions. **No end-to-end integration test** runs a full graph with mocked responses through all nodes. The parallel citation bug existed because nothing tested the merge→composer path.

**Mitigation:** Add integration test that mocks all LLM calls and verifies the full pipeline: plan → parallel research → merge → refinement loop → composer. Mock search tool with canned results.

### 2. "Strings Everywhere" Architecture

Nodes pass large text blobs. `parallel_researcher_node` returns a string. `merge_findings_node` concatenates strings. The deliverable searches for regex tags `[DELIVERABLE]` in strings. One node that forgets tag convention breaks Phase 2.

**Ideal:** `parallel_findings: list[ResearchFinding]` with `.citations`, `.confidence`, `.queries` fields. Three-layer DELIVERABLE defense wouldn't be necessary if types enforced tag presence.

**Trade-off:** Refactoring to Pydantic models between nodes is a major rewrite. Defer until a second agent is built that shares the research engine.

### 3. Evaluator Reliability

LLM-based evaluation is inherently unreliable. Even v4-pro grading v4-flash, it's still an LLM grading text. The numeric rubric mostly catches obvious failures (no citations, no structure) and passes everything else.

**Mitigation:**
- Make evaluation optional (skip when `CRITIC_MODEL` unset)
- Add human-in-the-loop override for critical research
- Consider rule-based pre-filter: has citations? has structure? has data? — only run LLM eval when ambiguous

### 4. Cache Complexity Exceeds Value

Cross-run cache: 300+ lines with TTL, delta checks, date detection, fuzzy matching. Hit rate is low due to LLM non-determinism (planner generates different goal wordings each run).

**Verdict:** Keep as opt-in (`--cache`) but don't invest further. Semantic chunking + vector retrieval would be over-engineering. Consider deprecating if maintenance burden grows.

### 5. Composer Prompt Bloat

Composer serializes the entire `sources` dict (up to 40+ entries) as JSON into the prompt. With verbose source metadata, this approaches token limits.

**Mitigation:** Pass only sources actually cited by Pass 1, or pre-summarize sources to title + URL + tier.

### 6. No Streaming to MCP Clients

MCP server runs in background thread, clients poll every 10-15s. Zero progress feedback during the 3-5 minute run.

**Ideal:** SSE streaming of partial results to MCP clients. Hard because the current architecture uses sync `graph.invoke()` in a thread. Would need async graph streaming with checkpoint-compatible state updates.

### 7. PDF Dependency is Heavy

Pandoc + weasyprint pulls in ~100MB system deps. Most users just want markdown.

**Mitigation:** Make PDF opt-in (`--pdf` flag) instead of automatic. Default: markdown only.

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
| `deep-research-langgraph-agent` | 13 production patterns: two-phase execution, 3-layer LLM constraints, Send API fan-out with citation extraction, subgraph refinement, numeric rubric evaluator, 5-stage citations, state pruning, circuit breaker, two-pass plan approval, SqliteSaver fallback, writable directory chain, progress tracking, MCP async patterns |
| `langgraph-agent-patterns` | StateGraph, Send API, subgraphs, interrupt/resume, checkpointing, JSON prompting, DELIVERABLE guarantee, circuit breaker, state pruning, progress markers, token tracking |
| `langgraph-agent-deployment/references/architecture-patterns.md` | Two-phase execution, refinement subgraph, Send API fan-out, circuit breaker, state pruning, progress markers, token tracking, auto-approve pattern |
| `langgraph-agent-deployment/references/quality-patterns.md` | Numeric rubric, per-claim confidence, source tiers, contradiction detection, DELIVERABLE guarantee, error surface |
| `langgraph-agent-deployment/references/pdf-generation.md` | Pandoc+weasyprint primary, Python fallback, Docker setup |
| `multi-agent-orchestration/references/langgraph-pipeline-patterns.md` | Send API, subgraphs, iteration loops, circuit breaker, interrupt/resume, JSON prompting |
