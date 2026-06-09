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
- [x] 48 tests (unit + E2E + HTTP/MCP route coverage)
- [x] Writable directory fallback chain for report output
- [x] SSE streaming endpoint for real-time progress
- [x] Checkpoint DB survives container recreation — named volume `research_checkpoints:/app/checkpoints` (June 2026)
- [x] Deep readiness check — `/ready` verifies config, report dir, checkpoint DB, LLM endpoint, and search backend

**Verdict:** Production-usable for single-user deployment. Supports concurrent research tasks within a single container. Checkpoints persist across deploys. Not production-grade for multi-tenant or mission-critical use. The remaining 7 operational gaps are alerting, runbook, rate limiting, horizontal scaling, request queuing, input sanitization, and versioned releases — none architectural.

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
- [x] Dashboard elapsed timer freezes on task completion/failed states instead of continuing to count
- [x] Concurrent execution (multiple research tasks run in parallel via asyncio.to_thread + isolated checkpoints)
- [x] Concurrent bugs fixed (os.environ race, thread_id collision, report filename collision)
- [x] PDF generation (opt-in via MCP `pdf: true` or dashboard checkbox, pandoc + weasyprint, `/download` route)
- [x] Checkpoint persistence (named Docker volume `research_checkpoints`, survives container recreation)
- [x] SearXNG version pinned (2026.6.2-e964708c0, was `:latest`)
- [x] Language-aware search (enrichment → planner annotation → researcher query generation in target language)
- [x] Search backend language propagation (SearXNG honors target language instead of forcing English)
- [x] Error page detection (404/403/500 detection in 4 languages, domain-root fallback, prevents synthesis from error pages)
- [x] Persisted dashboard history (`/tasks` merges memory + disk-backed task metadata)
- [x] Deep readiness endpoint (`/ready`)
- [x] HTTP/MCP route tests (`tests/test_mcp_server.py`) + CI Docker/MCP smoke coverage
- [x] CLI help without config + `ddgs` migration + README smoke-test cleanup

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

## Improvement Opportunities — Review Findings (June 2026)

Implemented. The review findings below were converted into shipped changes.

| Status | Area | What changed |
|---|---|---|
| ✅ | Deploy consistency | `docker-compose.yml` now matches `deploy.sh` for SearXNG pinning and checkpoint persistence (`research_checkpoints:/app/checkpoints`, `CHECKPOINT_DB_PATH=/app/checkpoints/checkpoints.db`). `deploy.sh start` also rebuilds the current image before restarting, so code changes are actually deployed. |
| ✅ | Search quality | Search now preserves explicit language hints end-to-end. SearXNG no longer forces English, Tavily routes non-English searches through SearXNG when available, and DDGS fallback maps hints to locale-specific regions. Added regression tests for diacritics, German-vs-Spanish inference, backend propagation, and planner-to-search language flow. |
| ✅ | Persistence / UX | `/tasks` now merges in-memory tasks with persisted `task_*.json` metadata, and the HTTP app hydrates recent completed tasks from disk on startup. Dashboard history survives restarts. |
| ✅ | Test coverage | Added `tests/test_mcp_server.py` covering POST `/mcp`, `/tasks`, `/ready`, `/download`, local/private-network dashboard gating, spoofed-header rejection, `/stream/{task_id}`, and dashboard load. Added GitHub Actions CI to run tests plus Docker/MCP smoke checks. |
| ✅ | Health checks | Added `/ready` for deep readiness checks while keeping `/health` as cheap liveness. Readiness verifies config presence, writable output/checkpoint paths, authenticated LLM endpoint reachability, and the active search backend with a real probe. |
| ✅ | Tooling / operator friction | `python -m app.cli --help` now works without API config. Pytest warning removed by dropping the stale asyncio config. Search dependency migrated to `ddgs`. README updated to the real env and smoke-test flow. |


## Unified Implementation Plan — Evidence-Structured, Audience-Aware Research Reports (June 2026)

### Goal

Upgrade the agent from a synthesis-first report generator into a blueprint-first, evidence-structured research system that produces audience-specific decision artifacts with auditable claims, source quality, and final report QA.

This plan unifies three inputs:

1. Internal deep research on deep-research agent architectures: critic pass, source scoring, outline-before-retrieval, sufficiency checks, budgeted/model-routed execution.
2. Review of the ChatGPT Deep Research PDF `SpaceX IPO Research for a Retail Investor.pdf`: strong audience framing, decision-support tables, scenario analysis, retail-specific checklist, and answer-first recommendation.
3. Existing project architecture: LangGraph two-phase execution, typed model bridge, citations, evaluator loop, MCP/dashboard runtime, Docker deployment.

### Product principles

- Audience first: the report shape should depend on who is deciding and what decision they need to make.
- Blueprint before retrieval: the planner should define required sections, tables, scenarios, evidence needs, and decision artifacts before research begins.
- Evidence before prose: synthesis should be backed by structured claims, sources, contradictions, and gaps, not only markdown findings.
- Critic after rendering: the final report artifact must be audited for unsupported claims, missing sections, hidden contradictions, and over-strong recommendations.
- YAGNI: ship deterministic schemas and simple heuristics before introducing Redis, vector stores, complex schedulers, or multi-agent coordination layers.

### Non-goals for this iteration

- No Redis/shared context store.
- No vector database.
- No full multi-agent rewrite.
- No token-budget-aware scheduler beyond simple per-run/per-section caps.
- No replacement of LangGraph or MCP runtime.
- No mandatory PDF formatting overhaul; markdown remains the canonical artifact.

### Target architecture delta

Current flow:

```text
planner → parallel researchers → merge → deliverable/evaluator/enhancer loop → composer → report
```

Target flow after this plan:

```text
topic enrichment
  → report blueprint planner
  → evidence-needs-aware parallel research
  → source scoring + evidence normalization
  → deliverable/evaluator/enhancer loop
  → component-based composer
  → final report critic
  → cited report + evidence appendix + QA summary
```

The key change is adding an explicit `ReportBlueprint` and evidence layer between planning, research, composition, and QA.

---

### Phase 1 — Report blueprint and audience-aware templates

**Objective:** Make the planner choose the right report shape before retrieval.

**Files:**
- Modify: `app/models.py`
- Modify: `app/state.py`
- Modify: `app/nodes/planner.py`
- Modify: `app/agent.py` — only if blueprint/evidence-needs metadata must be passed through `Send(...)` payloads
- Test: `tests/test_agent.py`

**Data model to add in `app/models.py`:**

```python
from typing import Literal
from pydantic import BaseModel, Field

ReportTemplate = Literal[
    "generic_research_report",
    "decision_memo",
    "retail_investor_memo",
    "architecture_review",
    "compare_and_recommend",
    "legal_policy_brief",
]

class ReportSectionSpec(BaseModel):
    title: str
    purpose: str
    required_evidence: list[str] = Field(default_factory=list)
    required_components: list[str] = Field(default_factory=list)

class ReportBlueprint(BaseModel):
    audience: str = "general"
    decision_context: str = ""
    template: ReportTemplate = "generic_research_report"
    sections: list[ReportSectionSpec] = Field(default_factory=list)
    required_tables: list[str] = Field(default_factory=list)
    required_scenarios: list[str] = Field(default_factory=list)
    required_decision_artifacts: list[str] = Field(default_factory=list)
    source_requirements: list[str] = Field(default_factory=list)
    confidence_policy: str = "State confidence for major claims and sections."
```

**State additions in `app/state.py`:**

```python
report_blueprint: Optional[dict]
"""Serialized ReportBlueprint produced by planner."""
```

**Planner behavior:**

- Extend topic enrichment to infer audience and decision context.
- Generate `ReportBlueprint` from the enriched topic and plan in both runtime paths: `generate_plan_only(...)` and `planner_node(...)`. Do not let CLI/MCP and direct graph invocation diverge.
- Prefer a shared helper, e.g. `generate_blueprint_and_sections(...)`, so template selection, section generation, and fallback behavior live in one place.
- Keep `report_sections` for backward compatibility, but derive it from blueprint sections.
- Use deterministic fallback if the LLM returns malformed blueprint JSON.
- If researchers need blueprint/evidence-needs context, update `app/agent.py` routing so `Send(...)` includes the relevant serialized blueprint or per-goal evidence need, not only `current_goal`.

**Template-selection heuristics:**

- If topic includes “should I invest”, “IPO”, “stock”, “retail investor” → `retail_investor_memo`.
- If topic asks “should we choose/build/adopt” → `decision_memo`.
- If topic asks architecture/system/design improvement → `architecture_review`.
- If topic asks compare/rank/best → `compare_and_recommend`.
- If topic is legal/regulatory/jurisdiction-specific → `legal_policy_brief`.
- Else → `generic_research_report`.

**Tests first:**

- `test_selects_retail_investor_template_for_ipo_question`
- `test_selects_architecture_review_template_for_agent_architecture_topic`
- `test_blueprint_fallback_preserves_existing_report_sections_when_json_invalid`
- `test_generate_plan_only_returns_report_blueprint`
- `test_planner_node_returns_report_blueprint`
- `test_parallel_researcher_receives_blueprint_evidence_needs` if `Send(...)` payloads are extended

**Acceptance criteria:**

- Planner returns a valid serialized blueprint for normal runs.
- CLI/MCP (`generate_plan_only`) and direct graph invocation (`planner_node`) populate `report_blueprint` consistently.
- Existing tests still pass without requiring all callers to use blueprint immediately.
- `report_sections` remains populated for composer compatibility.

---

### Phase 2 — Structured evidence model and source appendix

**Objective:** Make reports auditable by storing major claims, source support, contradictions, and gaps as structured state.

**Files:**
- Modify: `app/models.py`
- Modify: `app/state.py`
- Modify: `app/tools/citations.py`
- Modify: `app/nodes/researcher.py`
- Modify: `app/agent.py` if global source allocation belongs at merge/fan-in boundaries
- Test: `tests/test_agent.py`

**Models to add:**

```python
class EvidenceSource(BaseModel):
    source_id: str
    title: str = ""
    url: str
    domain: str = ""
    tier: int = Field(default=3, ge=1, le=3)
    source_type: str = "unknown"  # official, academic, company, news, analyst, community
    authority_reason: str = ""
    used_for_claims: list[str] = Field(default_factory=list)

class EvidenceClaim(BaseModel):
    claim_id: str
    text: str
    section: str = ""
    confidence: int = Field(default=3, ge=1, le=5)
    support_source_ids: list[str] = Field(default_factory=list)
    contradicting_source_ids: list[str] = Field(default_factory=list)
    evidence_strength: str = "medium"  # high, medium, low
    needs_followup: bool = False

class EvidenceGap(BaseModel):
    gap_id: str
    description: str
    why_it_matters: str
    attempted_queries: list[str] = Field(default_factory=list)
    impact_on_conclusion: str = "unknown"

class Contradiction(BaseModel):
    contradiction_id: str
    claim_a: str
    claim_b: str
    source_ids: list[str] = Field(default_factory=list)
    resolution: str = "unresolved"
```

**State additions:**

```python
evidence_claims: Annotated[list, operator.add]
evidence_gaps: Annotated[list, operator.add]
contradictions: Annotated[list, operator.add]
source_scores: Annotated[dict, operator.or_]
```

**Model consolidation rule:**

Do not create three competing source schemas. Keep `state.sources` as the canonical source register and extend its dict shape minimally toward `EvidenceSource`. Existing `Citation` / `CitationSource` wrappers can remain as boundary adapters, but all global IDs, source scores, and appendix rows must come from `state.sources`.

**Critical prerequisite — global source IDs:**

Parallel researchers may create local `src-1`, `src-2`, etc. Those IDs are not globally stable. At merge/fan-in, normalize all sources through `url_to_short_id` as the canonical allocator. Never trust a per-finding local `short_id` from a parallel worker as the global ID.

**Implementation approach:**

- Start with deterministic extraction from existing findings:
  - URLs and markdown links become canonical `state.sources` entries.
  - `[CONFIDENCE:N]` tags become claim confidence hints; preferably parse them into `ResearchFinding.confidence_tags` inside `_research_single_goal()` rather than reparsing only at composer time.
  - Lines prefixed with `CONTRADICTION:` become `Contradiction` records.
  - Phrases like “not found”, “missing”, “could not retrieve”, “unconfirmed” become `EvidenceGap` candidates.
- Append the Evidence Appendix deterministically after `replace_citation_tags(...)`. Do not ask the LLM to invent appendix rows.
- Do not introduce an LLM claim extractor in the first pass. Add it later only if deterministic extraction is insufficient.

**Source appendix output:**

Composer should be able to render:

```markdown
## Evidence Appendix

### Source Register
| Source | Tier | Type | Used for | Notes |
|---|---:|---|---|---|

### Major Claims
| Claim | Confidence | Evidence | Caveat |
|---|---:|---|---|

### Missing Evidence
| Gap | Why it matters | Impact |
|---|---|---|
```

**Tests first:**

- `test_extracts_evidence_claims_from_confidence_tags`
- `test_extracts_contradictions_from_findings`
- `test_extracts_missing_evidence_register_from_gap_language`
- `test_source_appendix_uses_stable_source_ids`
- `test_parallel_findings_do_not_collide_source_ids`
- `test_research_single_goal_populates_confidence_tags_from_summary`
- `test_evidence_appendix_is_rendered_from_state_not_llm_prose`

**Acceptance criteria:**

- Every report can include an evidence appendix without another web search.
- Source IDs are stable within a run and cannot collide across parallel findings.
- The appendix does not duplicate raw URL dumps; it summarizes source purpose and claim coverage.
- Phase 2 may use existing citation tiers only; Phase 3 enriches source ordering/scoring later.

---

### Phase 3 — Source scoring before synthesis

**Objective:** Prefer authoritative, recent, relevant, diverse sources before the composer sees them.

**Files:**
- Modify: `app/tools/citations.py`
- Modify: `app/models.py`
- Modify: `app/nodes/researcher.py`
- Test: `tests/test_agent.py`

**Scoring heuristic:**

```text
score = authority + relevance + recency + diversity - duplication_penalty - low_quality_penalty
```

For v1, only score fields that are actually captured. Current synthesized findings usually preserve URL/title/tier, not raw search snippets, search rank, query, or detected publication date. Either capture raw search result metadata in `ResearchFinding` / a `SourceCandidate` model before scoring, or explicitly limit v1 scoring to URL/domain/title/tier.

Initial deterministic weights:

| Signal | Points |
|---|---:|
| Official/government/company filing/source-of-record | +40 |
| Academic/standards/primary technical docs | +30 |
| Reputable industry or financial publication | +20 |
| Community/forum/social post | +5 |
| URL/title/snippet contains core query terms | +0..20 |
| Recent date detected for time-sensitive topic | +0..15 |
| Same-domain duplicate | -15 |
| Obvious SEO/content farm | -25 |

**Tests first:**

- `test_source_scoring_prioritizes_official_filing_over_news`
- `test_source_scoring_penalizes_duplicate_domains`
- `test_source_scoring_marks_community_sources_low_authority`
- `test_researcher_serializes_sources_sorted_by_score_for_composer`
- `test_source_candidate_preserves_query_rank_snippet_when_available` if snippet/recency scoring is implemented

**Acceptance criteria:**

- Composer receives source metadata sorted by source score for the evidence appendix.
- Key claims should prefer top-scored sources where available.
- No network calls required for scoring; use captured URL/domain/title/tier metadata, and only use snippet/date/query/rank if the researcher explicitly stores them.

---

### Phase 4 — Component-based composer and audience-specific report blocks

**Objective:** Copy the useful presentation strengths from the ChatGPT retail-investor PDF without copying its weak evidence traceability.

**Files:**
- Modify: `app/nodes/composer.py`
- Modify: `app/models.py`
- Test: `tests/test_agent.py`

**Implementation constraint:**

Do not build a large template engine in v1. Implement template defaults as ordered heading/block lists plus composer prompt instructions. The Evidence Appendix is the only deterministic renderer required initially. Extract classes/renderers later only when repeated logic proves it is needed.

**Component blocks to support:**

| Component | Purpose | Templates using it |
|---|---|---|
| `answer_first_summary` | Direct answer + main reasons | all |
| `what_is_being_decided` | Clarify actual exposure/choice/tradeoff | decision, investor, architecture |
| `key_facts_table` | Compact facts | decision, investor, compare |
| `timeline` | Dates/events | investor, legal/policy, market |
| `economics_or_mechanics` | How the thing works | investor, architecture, technical |
| `scenario_table` | bear/base/bull or option A/B/C | decision, investor, compare |
| `risk_table` | risks, probability/impact, evidence | decision, investor, architecture |
| `decision_checklist` | user-specific go/no-go checklist | decision, investor |
| `recommendation_block` | explicit action and caveats | decision, investor, compare |
| `open_questions` | unresolved items | all |
| `evidence_appendix` | auditability | all standard-depth reports |

**Template defaults:**

- `retail_investor_memo`: executive summary, what is being offered, business/economics, valuation scenarios, risk table, retail checklist, recommendation, open questions, evidence appendix.
- `architecture_review`: executive summary, current architecture, options/tradeoffs, implementation roadmap, risks, recommendation, evidence appendix.
- `decision_memo`: executive summary, decision context, options, criteria, scenarios, recommendation, caveats, evidence appendix.
- `compare_and_recommend`: executive summary, comparison matrix, scoring rationale, recommendation, caveats, evidence appendix.
- `legal_policy_brief`: question presented, authority hierarchy, controlling sources, ambiguity, practical answer, caveats, evidence appendix.

**Composer constraints:**

- Keep markdown as source of truth.
- Use existing `<cite source="src-N" />` tags and replacement pipeline.
- Keep inline citations for readability.
- Add appendices for auditability.
- Avoid detached numeric endnotes as the only citation system.

**Tests first:**

- `test_composer_uses_retail_investor_template_blocks`
- `test_composer_uses_architecture_review_template_blocks`
- `test_composer_includes_evidence_appendix_for_standard_depth`
- `test_brief_depth_omits_evidence_appendix_and_long_tables`
- `test_composer_preserves_existing_citation_replacement`

**Acceptance criteria:**

- A retail-investor-style topic produces decision-support sections, not a generic research report.
- Architecture topics produce a roadmap/tradeoff/report shape.
- Reports remain cited markdown and existing PDF generation still works.

---

### Phase 5 — Final report critic pass

**Objective:** Audit the rendered report, not just intermediate findings.

**Files:**
- Create: `app/nodes/report_critic.py`
- Modify: `app/agent.py`
- Modify: `app/state.py`
- Modify: `app/config.py`
- Modify: `app/nodes/composer.py`
- Modify: `app/mcp_server.py` — stage labels/progress/status must account for the post-composer critic
- Test: `tests/test_agent.py`
- Test: `tests/test_integration.py`
- Test: `tests/test_mcp_server.py`

**Critic checks:**

- Required blueprint sections are present.
- Required decision artifacts are present.
- Major factual claims have citations.
- Recommendation strength matches evidence strength.
- Low-confidence claims are hedged.
- Contradictions are not hidden.
- Missing evidence is disclosed.
- Evidence appendix exists for standard-depth reports.

**State additions:**

```python
report_critic_result: Optional[dict]
report_critic_passed: bool
```

**Config:**

```python
enable_report_critic: bool = field(default_factory=lambda: os.getenv("ENABLE_REPORT_CRITIC", "true").lower() not in {"0", "false", "no"})
```

**Routing policy:**

- Insert `report_critic` after `composer` in `app/agent.py`.
- Add `report_critic` to MCP progress maps and `STAGE_LABELS`.
- Start with critic as post-composer QA. It writes `report_critic_result` and `report_critic_passed`; it may append a short QA summary to the report, but should not discard useful reports.
- Define hard failures narrowly: no final report, no citations at all in standard mode, or missing all required blueprint sections. Other issues complete with `report_critic_passed=False` and a QA summary.
- Do not add a composer regeneration loop in the first version. Regeneration can come later if the critic produces stable, actionable fixes.

**Tests first:**

- `test_report_critic_fails_missing_required_section`
- `test_report_critic_fails_uncited_major_claim`
- `test_report_critic_flags_unresolved_contradiction`
- `test_report_critic_passes_complete_cited_report`
- `test_graph_runs_report_critic_after_composer_when_enabled`
- `test_report_critic_can_be_disabled_by_config`
- `test_mcp_status_includes_report_critic_result`
- `test_report_critic_stage_label_is_exposed_in_tasks_api`

**Acceptance criteria:**

- Standard reports include a short final QA summary or metadata record.
- Missing required sections and uncited major claims are caught in tests.
- Existing reports still complete if critic is disabled.

---

### Phase 6 — Missing-evidence register and sufficiency-driven re-planning

**Objective:** Stop passively saying “data missing”; actively decide whether missing evidence should trigger more research or weaken the recommendation.

**Files:**
- Modify: `app/nodes/evaluator.py`
- Modify: `app/nodes/enhancer.py`
- Modify: `app/nodes/researcher.py`
- Modify: `app/models.py`
- Test: `tests/test_agent.py`
- Test: `tests/test_integration.py`

**Sufficiency model:**

```python
class SufficiencyAssessment(BaseModel):
    information_sufficient: bool
    blocking_gaps: list[str] = Field(default_factory=list)
    follow_up_queries: list[str] = Field(default_factory=list)
    recommendation_strength: str = "medium"  # high, medium, low, no_recommendation
```

**Routing policy:**

- If evidence gaps are non-blocking: continue, disclose them.
- If gaps affect the main recommendation and iterations remain: route to enhancer with targeted queries.
- If gaps remain after max iterations: continue but downgrade recommendation strength and disclose why.
- Update the existing circuit breaker carefully: blocking blueprint-required gaps may override score-stagnation only while iterations remain; after max iterations, do not loop forever.

**Deferral note:** This phase should not start until Phases 1, 2, 4, and 5 are stable. Sufficiency routing depends on trustworthy blueprint/evidence state.

**Tests first:**

- `test_evaluator_marks_missing_comparator_data_as_blocking_when_required_by_blueprint`
- `test_enhancer_receives_gap_specific_followup_queries`
- `test_report_downgrades_recommendation_when_blocking_gap_remains_after_max_iterations`

**Acceptance criteria:**

- Missing required evidence becomes a structured register.
- The agent either researches the gap or explicitly downgrades confidence/recommendation strength.

---

### Phase 7 — Simple budgets and model routing

**Objective:** Add cost discipline without complex scheduling.

**Files:**
- Modify: `app/config.py`
- Modify: `app/state.py`
- Modify: `app/nodes/researcher.py`
- Modify: `app/tokens.py`
- Test: `tests/test_agent.py`

**Config additions:**

Use env-backed `field(default_factory=...)` values, matching the current `ResearchConfig` pattern:

```python
max_sources_per_goal: int = field(default_factory=lambda: int(os.getenv("MAX_SOURCES_PER_GOAL", "8")))
max_queries_per_goal: int = field(default_factory=lambda: int(os.getenv("MAX_QUERIES_PER_GOAL", "5")))
max_findings_chars_per_goal: int = field(default_factory=lambda: int(os.getenv("MAX_FINDINGS_CHARS_PER_GOAL", "12000")))
critic_model: str  # already exists; ensure report critic uses it
```

Add validation bounds so invalid env values fail clearly instead of crashing mid-run.

**Policy:**

- Worker model: planning, research summarization, composition.
- Critic model: evaluator and final report critic.
- Deterministic functions: source scoring, evidence appendix assembly, simple template selection.

**Tests first:**

- `test_researcher_respects_max_queries_per_goal`
- `test_researcher_caps_sources_per_goal`
- `test_report_critic_uses_critic_model_not_worker_model`

**Acceptance criteria:**

- Budgets are visible in config and respected by researcher.
- No sophisticated scheduler added.

---

### Phase 8 — Runtime, dashboard, and docs integration

**Objective:** Preserve existing MCP/dashboard behavior while exposing new report quality metadata.

**Files:**
- Modify: `app/mcp_server.py`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `ARCHITECTURE.md`
- Modify: `ROADMAP.md`
- Test: `tests/test_mcp_server.py`

**MCP/dashboard additions:**

- Include `template`, `audience`, and `report_critic_passed` in task metadata.
- Show report QA status in dashboard task card.
- Keep `/tasks` sanitized; do not expose absolute paths.
- Keep `/download` path traversal guard.

**Tests first:**

- `test_tasks_endpoint_includes_report_template_and_qa_status`
- `test_research_status_includes_report_critic_summary_when_available`
- `test_dashboard_renders_quality_status_without_exposing_paths`

**Acceptance criteria:**

- Existing MCP clients still work.
- Dashboard surfaces the new metadata without breaking current UI.
- Docs explain templates, evidence appendix, and critic behavior.

---

### Verification plan

Run after each phase:

```bash
cd /home/jorge/Documents/projects/deep-research-langgraph
.venv/bin/python -m pytest tests/ -q
git diff --check
```

Run before merging/pushing implementation:

```bash
cd /home/jorge/Documents/projects/deep-research-langgraph
.venv/bin/python -m pytest tests/ -q
docker build -t deep-research-agent .
bash deploy.sh start
curl -sf http://localhost:8100/health
curl -sf http://localhost:8100/ready
curl -sf http://localhost:8100/tasks
```

Manual smoke tests before final commit:

1. Run a retail-investor-style topic and verify it uses decision-support sections.
2. Run an architecture-improvement topic and verify it uses architecture-review sections.
3. Verify standard reports include evidence appendix and critic QA metadata.
4. Verify brief reports stay concise.
5. Verify dashboard still loads and report downloads still work.
6. Run one direct graph smoke test with `report_critic` enabled and disabled.
7. Run one MCP smoke test and verify `research_status` includes template and critic metadata.

### Implementation order and commit boundaries

Treat this as a roadmap, not one giant implementation batch.

| Milestone | Scope | Stop condition | Status |
|---|---|---|---|---|
| A | Phases 1, 2, and minimal Phase 4 | Blueprint + deterministic evidence appendix + template headings work; no report critic failure behavior yet | ✅ Complete (5017adb) |
| B | Phase 5 | Final critic records QA metadata and surfaces it through MCP/dashboard; hard failures narrowly defined | ✅ Complete (acd79aa) |
| C | Phases 3, 6, 7, 8 | Source scoring, sufficiency routing, budgets, and dashboard polish after evidence state is stable | ✅ Complete (f7c5219) |
| — | Contradiction + source diversity | Contradiction detection across claims, source diversity scoring, Final QA integration | ✅ Complete (5d9f0cb) |
| — | Duplicate source detection | Detect same URL under different src-IDs in source register | ✅ Complete (01512ae) |
| — | Claim extraction + gap filtering + QA hardening | Populate Major Claims table, filter meta-commentary from evidence gaps, hardened semantic QA prompt | ✅ Complete (8c00eba) |

Suggested commit boundaries inside those milestones:

| Commit | Scope | Status |
|---|---|---|---|
| 1 | Add blueprint models, state fields, planner fallback, tests | ✅ Done |
| 2 | Add evidence models/extraction/source appendix, tests | ✅ Done |
| 3 | Add source scoring, tests | ✅ Done |
| 4 | Add component-based composer templates, tests | ✅ Done |
| 5 | Add final report critic node, graph routing, tests | ✅ Done |
| 6 | Add sufficiency/gap-driven enhancer routing, tests | ✅ Done |
| 7 | Add simple budgets/model routing, tests | ✅ Done |
| 8 | Add MCP/dashboard/docs integration, deploy verification | ✅ Done |
| 9 | Add contradiction detection + source diversity scoring | ✅ Done (5d9f0cb) |
| 10 | Add duplicate source detection in critic | ✅ Done (01512ae) |
| 11 | Claim extraction, gap filtering, hardened semantic QA | ✅ Done (8c00eba) |

### Self-critique of this plan

| Finding | Impact | Adjustment |
|---|---|---|
| The highest-risk part is adding too much schema at once. | Could slow implementation and create brittle LLM JSON parsing. | Use deterministic fallback and keep `report_sections`/string findings compatible until each phase is proven. |
| A composer regeneration loop after final critic sounds attractive but is premature. | Could create unstable loops and higher cost. | First version only audits and exposes failures; regeneration can be a later phase. |
| Source scoring can become fake rigor if numeric scores are over-precise. | Users may over-trust arbitrary weights. | Treat scores as ordering heuristics, not final truth. Expose source tier/type/reason, not only number. |
| Claim extraction from prose is hard. | LLM extraction could hallucinate structured claims. | First implementation uses existing confidence tags, citations, contradiction markers, and gap language. Add LLM extraction only after deterministic path works. |
| Template selection can misclassify ambiguous topics. | Wrong report shape harms output. | Keep template override possible later; use conservative fallback to generic report. |
| More appendices can make reports bloated. | User experience may worsen for brief/simple topics. | Evidence appendix only for `standard` depth; brief mode remains short. |
| Dashboard metadata changes can leak paths or internals. | Security regression risk. | Keep existing sanitization tests and add explicit tests for new fields. |
| Retail/legal templates may imply domain expertise beyond current search pipeline. | Legal/policy and financial outputs may be over-trusted. | For v1, templates are presentation and audit structures, not guarantees of legal/financial-grade analysis. Domain-specific critic rules can come later. |

### Final priority recommendation

Start with Phases 1, 2, 4, and 5. They deliver the visible product jump: audience-aware report structure, evidence appendix, decision-support components, and final report QA.

Defer Phases 6 and 7 until the evidence model is stable. Adaptive re-planning and budgets are valuable, but they depend on the blueprint/evidence layer being trustworthy first.

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

## Quality Hardening — Post-Evaluation Improvements

*Plan written 2026-06-08 after 3 live agent evaluations exposing 8 quality issues across the quality-control layer.*

### Root Cause Analysis

Three live runs surfaced the same failure pattern: **features passed unit tests but failed in production** because unit tests used synthetic data that didn't match real LLM output. The claim extractor regex matched `<cite source="src-1"/>` but the LLM generates `<cite src="1"/>`. Heading checks used exact set membership but real headings have descriptive suffixes. Evidence gap regex caught meta-commentary that only appears in refinement-loop output.

**Core insight:** The test suite validates pipeline structure (does the graph compile? do nodes return state?) but doesn't validate quality-control behavior with real LLM output patterns. This is a testing gap, not a logic gap.

### Priority Tiers

| Priority | Criteria | Items |
|----------|----------|-------|
| **P1** — Shipping bugs | Fixes defective behavior visible in live output | Claim text quality, source dedup, claim extraction fallback, gap regex hardening |
| **P2** — Verification gaps | Features that have never been proven to work in production | Contradiction detection test, integration tests with real output, critic model check |
| **P3** — Polish | Works correctly but output quality degrades UX | Clean claim text rendering |

### Task Breakdown

#### P1.1 — Sanitize claim text in Major Claims table
- **Problem:** Extracted claims include raw `<cite>` tags and markdown headers in the displayed text. Example: `"Introduction and Foundational Definitions ### 1.1 Defining AI Agents... <cite source=\"src-1\" />"`
- **Fix:** `_extract_claims_from_report` should strip `<cite>` tags and markdown heading prefixes (`###`, `##`) from claim text before storing. Truncate to 200 chars with ellipsis.
- **Files:** `app/nodes/composer.py`
- **Test:** Extract claims from a report with `<cite>` tags, verify no angle brackets or heading markers in claim text.
- **Stop condition:** Run on 3 live reports, verify all claim text is clean prose.

#### P1.2 — Deduplicate sources in composer, not just warn
- **Problem:** Every report has 17-40 duplicate source entries. The critic warns about them but doesn't fix them. The composer should deduplicate before building the appendix.
- **Fix:** In `build_evidence_appendix`, deduplicate the sources dict by URL before rendering the Source Register. Keep the first occurrence of each URL and drop subsequent ones. Update `used_for_claims` references.
- **Files:** `app/nodes/composer.py`
- **Test:** Build appendix with sources dict containing duplicate URLs, verify deduplicated output.
- **Stop condition:** Live test shows 0 duplicate source warnings.

#### P1.3 — Claim extraction fallback for inline URL citations
- **Problem:** If the LLM generates inline markdown links (`[Title](URL)`) instead of `<cite>` tags, the extractor finds zero claims. The post-mortem report had this exact failure mode.
- **Fix:** Add a second extraction pass in `_extract_claims_from_report`: if the `<cite>`/`[src-N]` pass yields < 3 claims, scan for markdown links `[text](url)` and extract the surrounding text as backup claims. Map URLs to src-IDs using the sources dict.
- **Files:** `app/nodes/composer.py`
- **Test:** Extract claims from report with only inline URL citations (no `<cite>` tags), verify ≥1 claim found.
- **Stop condition:** Post-mortem-style report with inline URLs produces populated Major Claims table.

#### P1.4 — Harden evidence gap regex against additional meta-commentary patterns
- **Problem:** The regex filter excludes "search results", "original evaluation", "previously missing", "filling missing" — but there may be other meta-commentary patterns from refinement passes.
- **Fix:** Add exclusion patterns for: "Impact on previous findings", "deficiencies identified", "addressed in", "updated comparison", "synthesis incorporates". Test against the actual evidence_gaps from the live reports.
- **Files:** `app/nodes/enhancer.py`, `app/agent.py` (merge_findings)
- **Test:** Run gap extraction on the refinement-pass output that caused the original contamination, verify zero meta-commentary gaps.
- **Stop condition:** Live test Missing Evidence table contains only real evidence gaps, zero refinement notes.

#### P2.1 — Prove contradiction detection works with a real trigger case
- **Problem:** Contradiction detection has never fired across 3 live runs. Either it works but real reports don't trigger it, or the evidence_claims format doesn't match what the detector expects.
- **Fix:** Create a synthetic report with two high-confidence claims from different sources that directly oppose each other on the same topic. Run through the full pipeline and verify the contradiction appears in Final QA.
- **Files:** `tests/test_integration.py` (add integration test), possibly `app/nodes/evaluator.py` if bugs found
- **Test:** Integration test: feed two opposing claims through evaluator, verify contradiction in sufficiency_assessment.
- **Stop condition:** Contradiction detection fires in at least one live or synthetic run, produces expected output in Final QA.

#### P2.2 — Add integration tests exercising real LLM output patterns
- **Problem:** Unit tests use synthetic state dicts that don't match real LLM output. Bugs like "regex doesn't match actual `<cite>` format" only surface in live testing.
- **Fix:** Add 3 integration tests that run the composer with real-looking report text (from saved live reports, anonymized). Verify: Major Claims table populated, no duplicate sources, clean claim text, no meta-commentary in gaps.
- **Files:** `tests/test_integration.py`
- **Test:** Feed actual report text from a live run into compose + critic pipeline, verify all quality gates pass correctly.
- **Stop condition:** All 3 saved reports produce correct quality output (no false FAIL, populated tables, real warnings).

#### P2.3 — Warn when critic model equals worker model
- **Problem:** If `CRITIC_MODEL` is the same as `WORKER_MODEL`, semantic QA quality degrades silently (LLMs grading their own output inflates scores).
- **Fix:** In `report_critic_node`, compare `config.critic_model` to `config.worker_model`. If equal, add a warning: "Critic model equals worker model — QA quality may be inflated."
- **Files:** `app/nodes/report_critic.py`
- **Test:** Set CRITIC_MODEL=deepseek-v4-flash, WORKER_MODEL=deepseek-v4-flash, verify warning in Final QA.
- **Stop condition:** Warning appears when models match, absent when they differ.

#### P3.1 — Polish claim text rendering
- **Problem:** Claim text starts mid-sentence or includes formatting artifacts from markdown parsing.
- **Fix:** After extracting claim text, strip leading punctuation/conjunctions ("- ", "* ", "**"), trim to sentence boundaries, cap at 200 chars with "..." only if truncated mid-word.
- **Files:** `app/nodes/composer.py`
- **Test:** Extract claims from reports with bullet lists, bold headers, verify clean prose output.
- **Stop condition:** 3 live reports show consistently clean, readable claim text.

### Plan Self-Critique

**Risk: Source dedup breaks citation references.** P1.2 deduplicates the sources dict by URL, keeping the first src-N and dropping duplicates. But report body citations use the original src-IDs. If src-5 is a duplicate of src-1, dropping src-5 means any `<cite src="5"/>` in the report body won't resolve. Mitigation: build a remapping dict (`old_id → canonical_id`) and rewrite citation references in the report body. Test: after dedup, every `<cite>` tag in the report resolves to an existing source.

**Gap: No "empty table suppression" task.** The critic warns about empty Major Claims and Missing Evidence tables. The fix shouldn't just populate them — it should also suppress them entirely when there's no data. Add P1.5: `build_evidence_appendix` omits Major Claims and Missing Evidence sections when their data lists are empty (not just the whole appendix).

**Gap: Semantic QA prompt doesn't explicitly catch "arbitrary percentage as production note."** Our prompt mentions "unsupported quantitative claims" generally. The "20% optional parameters" and "3-5 core tasks" patterns should be called out explicitly as examples since they recur. Add to P1 task: update semantic QA prompt with concrete examples of this failure pattern.

**Ordering efficiency:** P1.1, P1.2, P1.3, and P1.5 all touch `app/nodes/composer.py`. Implement them together in one pass to avoid merge conflicts and redundant test runs.

**Testing strategy:** P2.2 (integration tests with real output) should be implemented FIRST — before P1 fixes — to establish a baseline. The integration tests should fail initially (proving they catch the bugs), then pass after P1 fixes. This follows TDD: red tests from real output patterns, then fix.

### Revised Execution Order

1. P2.2 — Write integration tests with real LLM output (RED — should fail)
2. P1.1 + P1.2 + P1.3 + P1.5 — Fix composer (claim sanitization, source dedup with ID remapping, inline citation fallback, empty table suppression)
3. P1.4 — Harden evidence gap regex
4. P2.3 — Critic model equality check
5. P2.1 — Contradiction detection integration test
6. P3.1 — Polish claim text rendering
7. Full test suite + live test + docs + commit + push

### Hardening Complete — 2026-06-08

All P1 and P2 tasks completed across 4 commits. P3 (polish) deferred — contradiction detection needs real trigger data.

**Live test verification (run research-418f48ee7e77):**

| Feature | Result |
|---------|--------|
| Major Claims table | Populated with clean claim text, zero `<cite>` tags |
| Source deduplication | Zero duplicate source warnings (was 26-40) |
| Empty table suppression | Empty sections omitted entirely |
| Claim extraction | Two-pass: `<cite>` primary + inline URL fallback |
| Semantic QA warnings | All real, no false positives |
| Evidence gap filtering | Zero meta-commentary leakage |
| Heading matching | Substring — no false "section missing" |
| Artifact matching | Lenient fallback — no false "artifact missing" |
| Section checking | Correctly identifies genuinely missing blueprint sections |
| Test suite | 83/83 passing (6 new integration tests) |

**Remaining:** P2.3 contradiction detection (needs trigger data), P3.1 claim text polish.

## Resilience Hardening — Round 2 Improvements

*Plan written 2026-06-08 after 3-round live test exposed 2 systemic issues.*

### Findings from 3-round test

| Issue | Prevalence | Impact |
|-------|-----------|--------|
| API rate-limiting kills entire research run | 1/3 runs (run 2) | Complete task failure when Phase 2 enhancer hits rate limit. Phase 1 findings exist but are discarded. |
| Source duplicates at registration time | Every run (17-40 dups) | We deduplicate at render time but the root cause persists: `merge_findings_node` registers sources without checking for existing URLs. |

### Improvement 1: Graceful degradation on API failure

**Problem:** When Phase 2 enhancer LLM call fails (rate limit, transient error), the entire research task fails with "no working provider." Phase 1 findings — which completed successfully — are discarded.

**Fix:** Catch LLM errors in enhancer node and Phase 2 researcher. Instead of crashing, return findings from Phase 1 and proceed to composer. Add `graceful_degradation: True` to state so the Final QA can note the degraded status.

**Files:** `app/nodes/enhancer.py`, `app/agent.py` (refinement subgraph error handling)
**Test:** Mock LLM to raise an exception in enhancer, verify the graph continues to composer instead of failing.

### Improvement 2: Source dedup at registration time

**Problem:** `merge_findings_node` registers all sources from Phase 1 and Phase 2 without checking if URLs already exist. Every run produces 17-40 duplicate entries that the composer cleans up. Prevention is cheaper than cleanup.

**Fix:** In `merge_findings_node`, before adding a new source, check if its URL already exists in `all_sources`. If so, skip registration. Build a remapping dict (`new_id → existing_id`) so claim references stay consistent.

**Files:** `app/agent.py` (merge_findings_node)
**Test:** Feed findings with duplicate URLs, verify sources dict has zero duplicates.

### Stop condition

- Live test: research completes without total failure on rate-limited runs (graceful degradation proven)
- Live test: 0 duplicate source warnings (dedup prevention proven)
- 83+ tests passing

### Contradiction Detection Fix — 2026-06-08

**Root cause:** Detector ran in evaluator (Phase 1) but evidence_claims are extracted by composer (Phase 2). Empty list, zero firings.

**Fix:** Move to report_critic_node after claim extraction from report body. First live test on Vitamin D/COVID-19 topic detected 5 contradictions between 3 sources making opposing mortality-effect claims.

### P3 Polish Complete

Claim text now: strips connector words (and, but, however), capitalizes first letter, truncates at word boundaries (not mid-word), strips leading punctuation and markdown formatting.
