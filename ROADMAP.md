# Roadmap

## Production Readiness Review (PRR)

Assessment framework: pass/fail per item with concrete evidence. No letter grades — every item is checkable, every gap has a specific fix.

### 1. Monitoring & Observability — Can you detect breakage?

- [x] Health endpoint (`/health` → `{"status":"ok"}`)
- [x] Per-node token tracking with percentage breakdown
- [x] Structured logging (info/warning/error levels)
- [x] Progress markers at every pipeline stage (✓ 📦 📝 ✅ ❌ 🔧 📄)
- [ ] Alerting — no notification if container crashes or research fails
- [ ] Metrics export (Prometheus/Datadog) — token costs only visible in CLI

### 2. Incident Response — Can you fix it fast?

- [x] Actionable error messages (env validation blocks startup with fix instructions)
- [x] Graceful degradation (Playwright missing → returns `""`, SqliteSaver missing → MemorySaver)
- [x] Circuit breaker prevents runaway API costs on score stagnation
- [x] LLM provider fallback chain (primary → FALLBACK_API_KEY)
- [ ] Runbook — no documented recovery procedure for research failures
- [ ] Versioned releases — Docker `:latest` tag only, no rollback story

### 3. Security — Are vulnerabilities managed?

- [x] API keys via env vars (never hardcoded)
- [x] No eval/exec with user input
- [x] Docker network isolation (research-net)
- [ ] Input sanitization — research topics pass raw to LLM prompts
- [ ] Rate limiting — MCP endpoint has no request throttling

### 4. Scalability & Performance — Will it handle load?

- [x] Well-understood resource profile (single container, ~2GB RAM)
- [x] State pruning prevents O(N²) checkpoint bloat
- [x] Search fallback chain (Tavily → SearXNG → DuckDuckGo)
- [x] Concurrent execution — multiple research tasks run in parallel via `asyncio.to_thread` (June 2026). Unique thread IDs, isolated checkpoints, non-colliding filenames. Dashboard shows all tasks independently.
- [ ] Horizontal scaling — single container handles concurrent threads but no cross-container load distribution
- [ ] Request queuing — background thread with no pending request management

### 5. Operability — Can someone else run it?

- [x] One-command deploy (`deploy.sh start`)
- [x] Env var validation at startup (blocks on critical, warns on non-critical)
- [x] Comprehensive docs (AGENTS.md, ARCHITECTURE.md, ROADMAP.md)
- [x] 29 tests (25 unit + 4 E2E), all passing in ~10s
- [x] Writable directory fallback chain for report output
- [x] SSE streaming endpoint for real-time progress
- [ ] Checkpoint DB migration story — no schema versioning
- [ ] Deep health check — `/health` returns 200 even if LLM is unreachable

**Verdict:** Production-usable for single-user deployment. Supports concurrent research tasks within a single container. Not production-grade for multi-tenant or mission-critical use. The remaining 9 operational gaps are alerting, runbook, rate limiting, horizontal scaling, request queuing, deep health, input sanitization, checkpoint migration, and versioned releases — none architectural.

**Research quality improvements (May 2026):**
- Topic enrichment: raw user topics are pre-processed into structured research briefs with domain context and ambiguity detection
- Verification pass: after Phase 1 synthesis, cross-checks for domain mismatches (e.g., manufacturing PRR vs software PRR)
- Smarter browser: browser extraction for top result when HTTP content is sparse, with same-domain link following
- Domain disambiguation: planner prompt instructs LLM to identify terms with multiple meanings across domains

---

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
- [x] Self-documenting MCP tools (rich descriptions with HOW IT WORKS/OUTPUT FORMAT/TOPIC GUIDANCE; outputSchema removed — Hermes enforces it on results)
- [x] Stage labels in research_status (human-readable pipeline stage alongside numeric progress)
- [x] Web dashboard (`http://localhost:8100/`) — task list, progress bars, inline report viewer, launch form
- [x] Concurrent execution (multiple research tasks run in parallel via asyncio.to_thread + isolated checkpoints)
- [x] Concurrent bugs fixed (os.environ race, thread_id collision, report filename collision)
- [x] PDF generation (opt-in via MCP `pdf: true` or dashboard checkbox, pandoc + weasyprint, `/download` route)

## Technical Debt & Known Issues

Architectural concerns from code review (May 2026). Not blockers — the agent is production-usable — but areas for improvement.

### 1. Test Coverage vs Complexity

✅ **RESOLVED** (May 2026). Added E2E integration test suite (`tests/test_integration.py`) with 4 scenarios:
- Happy path: parallel research → merge → PASS → composer
- Enhancer loop: evaluator FAILs, enhancer runs, deliverable regenerates, PASS on retry
- Circuit breaker: identical FAIL scores trigger stagnation detection → force PASS
- Brief mode: `depth=brief` produces short executive summary

23 total tests (19 unit + 4 E2E). All scenarios mock LLM and search tool, running in ~10 seconds.

### 2. "Strings Everywhere" Architecture

✅ **PARTIALLY RESOLVED** (May 2026). Added `app/models.py` with `ResearchFinding`, `Citation`, `Deliverable`, `ConfidenceTag`, and `ResearchOutput` Pydantic models. `_research_single_goal()` now returns a typed `ResearchFinding` with pre-extracted citations, preventing the parallel citation loss bug at the type level.

**Type-safe accessors added (May 2026):** `findings_from_state()`, `findings_to_state()`, `get_typed_sources()` — typed wrappers around string-based LangGraph state. Parse and serialize findings without regex. Citation extraction at the type level.

**Remaining:** `parallel_findings` state field is still `list[str]` for LangGraph TypedDict compatibility with `operator.add` reducer. Full migration to typed models between all nodes requires custom reducers. The accessors provide the migration path.

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

✅ **RESOLVED** (May 2026). Added Playwright + Chromium browser extraction:
- `fetch_url_content()` uses two-stage extraction: HTTP first, browser fallback
- Automatic fallback when HTTP returns <500 chars (JS-rendered pages)
- Graceful degradation if Playwright not installed (ImportError catch)
- Removes script/nav/footer elements before text extraction
- 20s timeout per page, networkidle wait strategy
- Docker image includes Playwright + Chromium (~200MB larger)

### 9. Single LLM Provider Dependency

✅ **RESOLVED** (May 2026). Added fallback provider chain in `_TrackedChatOpenAI`:
- On invoke() failure, automatically retries with `FALLBACK_API_KEY`/`FALLBACK_API_BASE`
- Configurable via `FALLBACK_MODEL` (defaults to `WORKER_MODEL`)
- Logs warning when fallback activates so operators know there's an issue
- Pattern mirrors search fallback chain (Tavily → SearXNG → DuckDuckGo)

### 10. Env Var Management is Fragile

✅ **RESOLVED** (May 2026). Added `ResearchConfig.validate()` called at startup:
- CLI: blocks with exit 1 if WORKER_API_KEY or WORKER_API_BASE missing
- MCP server: logs error and exits if critical vars missing  
- Warns on non-critical issues (critic == worker model, high iteration count)
- 4 config validation tests added

### 11. No Per-Node Token Breakdown

✅ **RESOLVED** (May 2026). Added `token_breakdown: dict[str, int]` to state:
- `_TrackedChatOpenAI` accepts `node_name` parameter
- All 5 nodes annotated: planner, researcher, deliverable, evaluator, composer
- `operator.or_` reducer merges per-node dicts across invocations
- CLI displays per-node tokens with percentages after research completes
- Example output: `planner: 1,234 tokens (12.2%), researcher: 7,890 tokens (78.1%)`

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

✅ Done (May 2026). Two-stage extraction: HTTP first (fast, static pages), Playwright+Chromium fallback for JS-rendered pages. Graceful degradation if Playwright not installed.

## Skills Captured

| Skill | Content |
|-------|---------|
| `deep-research-langgraph-agent` | 23 production patterns: [existing ones], LLM fallback chain, env var validation, per-node tokens, browser-based research, type-safe state accessors |
| `langgraph-agent-patterns` | StateGraph, Send API, subgraphs, interrupt/resume, checkpointing, JSON prompting, DELIVERABLE guarantee, circuit breaker, state pruning, progress markers, token tracking |
| `langgraph-agent-deployment/references/architecture-patterns.md` | Two-phase execution, refinement subgraph, Send API fan-out, circuit breaker, state pruning, progress markers, token tracking, auto-approve pattern |
| `langgraph-agent-deployment/references/quality-patterns.md` | Numeric rubric, per-claim confidence, source tiers, contradiction detection, DELIVERABLE guarantee, error surface |
| `langgraph-agent-deployment/references/pdf-generation.md` | Pandoc+weasyprint primary, Python fallback, Docker setup |
| `multi-agent-orchestration/references/langgraph-pipeline-patterns.md` | Send API, subgraphs, iteration loops, circuit breaker, interrupt/resume, JSON prompting |
