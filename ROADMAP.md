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

✅ **RESOLVED** (May 2026). Added E2E integration test (`tests/test_integration.py`) that mocks LLM and search tool, runs full graph pipeline, and verifies parallel research → merge → refinement → composer path. 16 total tests (15 unit + 1 E2E).

**Remaining gaps (post-resolution):**
- E2E test only runs happy path (immediate PASS). Missing scenarios: enhancer loop on FAIL, circuit breaker on stagnation, brief mode executive summary.
- `_serialize_sources` function, brief mode composer path, multi-model critic vs worker distinction untested.
- FakeLLM doesn't exercise the evaluator LLM path or enhancer regeneration path.

### 2. "Strings Everywhere" Architecture

✅ **PARTIALLY RESOLVED** (May 2026). Added `app/models.py` with `ResearchFinding`, `Citation`, `Deliverable`, `ConfidenceTag`, and `ResearchOutput` Pydantic models. `_research_single_goal()` now returns a typed `ResearchFinding` with pre-extracted citations, preventing the parallel citation loss bug at the type level.

**Remaining:** `parallel_findings` state field is still `list[str]` for LangGraph TypedDict compatibility. Full migration to typed models between all nodes requires a larger refactor of the state schema.

### 3. Evaluator Reliability

✅ **MITIGATED** (May 2026). Added rule-based pre-check before LLM evaluation:
- CLEAR FAIL: 0 URLs, <200 chars, error keywords → skip LLM, return FAIL
- CLEAR PASS: 3+ URLs, quantitative data, structure, >400 chars → skip LLM, return PASS
- AMBIGUOUS: falls through to LLM evaluation (conservative)

Also added `ENABLE_EVALUATOR` env var to disable evaluation entirely (auto-PASS).

### 4. Cache Complexity Exceeds Value

✅ **DEPRECATED** (May 2026). Cross-run cache was 300+ lines with TTL, delta checks, date detection, fuzzy matching. Hit rate was low due to LLM non-determinism. All cache functions are now no-ops with deprecation warnings. Will be removed in a future release. The `--cache` CLI flag has been removed.

**Lesson:** Cross-run caching has diminishing returns for single-agent research tools. Fresh research with fast models is cheap enough.

### 5. Composer Prompt Bloat

✅ **RESOLVED** (May 2026). `_serialize_sources()` now only passes essential fields (`short_id`, `title`, `url`, `tier`) to the composer prompt, dropping `authority_reason` and `supported_claims` which the LLM doesn't need for citation writing.

### 6. No Streaming to MCP Clients

✅ **RESOLVED** (May 2026). Added SSE streaming endpoint `GET /stream/{task_id}`:
- Events: started, update (progress/stage), completed, failed, heartbeat
- Thread-safe: runner pushes via `call_soon_threadsafe`
- Heartbeats every 5s to keep connection alive
- Queue auto-creates per task, cleaned up on completion

### 7. PDF Dependency is Heavy

✅ **RESOLVED** (May 2026). PDF generation is now opt-in (`--pdf` flag). Default is markdown only. Saves ~100MB of system deps (pandoc/weasyprint) for most users.

### 8. No Browser-Based Research

🟡 **OPEN.** The agent fetches URL content (top 3 results, 5K chars each) and appends the full-page text to findings. This works for text-heavy pages but fails on:
- JavaScript-rendered content (SPAs, dashboards)
- Paywalled articles (Medium, WSJ)
- Interactive visualizations
- Cloudflare-protected pages

A headless browser node (Playwright/Puppeteer) would unlock research topics that are currently invisible. This is the single highest-leverage improvement for research depth.

**Effort:** Medium (2-3 days). **Impact:** High.

### 9. Single LLM Provider Dependency

🟡 **OPEN.** Both worker and critic use DeepSeek API. If DeepSeek is down, the agent is dead. The search backend has a nice Tavily → SearXNG → DuckDuckGo fallback chain, but there's no equivalent for the LLM.

Adding an OpenAI-compatible fallback (OpenRouter, local Ollama) would mirror the search fallback pattern and make the agent provider-agnostic.

**Effort:** Low (1 day). **Impact:** Medium.

### 10. Env Var Management is Fragile

🟡 **OPEN.** The `.docker.env` template works but `-e VAR` shell passthrough passes empty strings if VAR isn't set. The `WORKER_API_KEY="***"` pattern requires the key to be exported, which fails silently. Better ergonomics: explicit config validation at startup with clear error messages for missing required vars.

**Effort:** Low (half day). **Impact:** Medium (prevents new-user frustration).

### 11. No Per-Node Token Breakdown

🟡 **OPEN.** `total_tokens` is tracked globally but you can't see where tokens are going. Is the evaluator burning 40% of the budget? Is the planner generating 8K-token plans? Without per-node breakdown, cost optimization is guesswork.

Simple fix: `token_breakdown: dict[str, int]` updated by `get_llm()` when a `node` parameter is passed.

**Effort:** Low (1 day). **Impact:** Medium.

## Next — Polish

### Better model defaults

Both worker and critic default to DeepSeek V4 Flash. Stronger critic would catch more subtle issues.

✅ Done: documented in `.docker.env.template` with recommendation to use stronger CRITIC_MODEL.

### Streaming report output

Progress markers show milestones but user can't watch the report form.

✅ Done: composer now streams report to stdout token-by-token via `llm.stream()` with `flush=True`.

## Later — Big Features

### Cross-run memory

❌ **DEPRECATED** (May 2026). Goal-level cache with key phrase hashing, fuzzy matching, delta validation. Hit rate was fundamentally limited by LLM non-determinism. All functions are now no-ops with deprecation warnings. Cache file (`research_cache.db`) will be removed in a future release.

**Lesson:** Cross-run caching has diminishing returns for single-agent research tools. The planner generates different goal wordings each run, so exact and even fuzzy matching rarely hits. Semantic chunking + vector retrieval would add significant complexity for marginal benefit. Fresh research with fast models (v4-flash) is cheap enough that caching is not worth the code complexity.

**Original design (for reference):**
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

Current agent uses web search + text extraction (top 3 URLs, 5K chars each). Adding browser-based research would unlock:

- **JavaScript-rendered content** — SPAs, dashboards, interactive tools (Playwright/Puppeteer node)
- **Paywalled articles** — Medium, WSJ (archive.is fallback or authenticated sessions)
- **Structured data extraction** — tables, charts, APIs embedded in pages
- **Multi-page workflows** — search form → results → detail pages → extraction

This is the single highest-leverage improvement for research depth on modern web content.

## Skills Captured

| Skill | Content |
|-------|---------|
| `deep-research-langgraph-agent` | 17 production patterns: two-phase execution, 3-layer LLM constraints, Send API fan-out with citation extraction, subgraph refinement, numeric rubric evaluator, 5-stage citations, state pruning, circuit breaker, two-pass plan approval, SqliteSaver fallback, writable directory chain, progress tracking, MCP async patterns, composer serialization bloat fix, rule-based evaluator pre-check, PDF opt-in pattern, SSE streaming for MCP |
| `langgraph-agent-patterns` | StateGraph, Send API, subgraphs, interrupt/resume, checkpointing, JSON prompting, DELIVERABLE guarantee, circuit breaker, state pruning, progress markers, token tracking |
| `langgraph-agent-deployment/references/architecture-patterns.md` | Two-phase execution, refinement subgraph, Send API fan-out, circuit breaker, state pruning, progress markers, token tracking, auto-approve pattern |
| `langgraph-agent-deployment/references/quality-patterns.md` | Numeric rubric, per-claim confidence, source tiers, contradiction detection, DELIVERABLE guarantee, error surface |
| `langgraph-agent-deployment/references/pdf-generation.md` | Pandoc+weasyprint primary, Python fallback, Docker setup |
| `multi-agent-orchestration/references/langgraph-pipeline-patterns.md` | Send API, subgraphs, iteration loops, circuit breaker, interrupt/resume, JSON prompting |
