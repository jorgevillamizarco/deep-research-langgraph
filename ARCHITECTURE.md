# Architecture: Deep Research Agent

LangGraph-based deep research agent combining Google ADK's two-phase execution model with LangGraph's native parallelism. MCP server for external integration, Docker-deployable.

## High-Level Architecture

```mermaid
flowchart TB
    subgraph Entry["Entry Points"]
        CLI["CLI<br/>python -m app.cli"]
        MCP["MCP Server<br/>SSE + JSON-RPC"]
        Docker["Docker<br/>docker compose up"]
    end

    subgraph Graph["LangGraph StateGraph"]
        direction TB
        P["🧠 Planner<br/>plan + section outline<br/>+ human interrupt"]
        PR["🔍 Parallel Researchers<br/>Phase 1: N goals via Send API"]
        M["📦 Merge Findings<br/>fan-in from parallel"]
        subgraph Refine["Refinement Subgraph"]
            direction LR
            D["📝 Deliverable<br/>Phase 2: cross-goal synthesis"]
            E["⚖️ Evaluator<br/>numeric rubric ≥4/5"]
            EN["🔧 Enhancer<br/>follow-up queries"]
            D --> E
            E -->|FAIL| EN
            EN --> D
        end
        C["📄 Composer<br/>cited markdown report"]
        P --> PR
        PR --> M
        M --> Refine
        Refine -->|PASS| C
    end

    subgraph Search["Search Backend"]
        direction TB
        T["Tavily API"]
        S["SearXNG<br/>self-hosted"]
        DDG["DuckDuckGo<br/>fallback"]
        T --> S --> DDG
    end

    subgraph Output["Output"]
        MD["Markdown Report<br/>with structured citations"]
        Vol["Docker Volume<br/>/data"]
    end

    CLI --> Graph
    MCP --> Graph
    Docker --> Graph
    Graph --> Search
    Graph --> Output
```

## Two-Phase Execution Model

```mermaid
sequenceDiagram
    actor User
    participant Planner
    participant Phase1 as Phase 1: Researchers
    participant Merge
    participant Phase2 as Phase 2: Deliverable
    participant Evaluator
    participant Enhancer
    participant Composer

    User->>Planner: research topic
    Planner->>Planner: generate plan with [RESEARCH]/[DELIVERABLE] goals
    Planner-->>User: interrupt: approve plan?
    User->>Planner: approved + feedback
    Planner->>Phase1: fan-out N [RESEARCH] goals via Send API
    Note over Phase1: parallel execution across goals
    Phase1->>Phase1: generate queries → search → synthesize
    Phase1-->>Merge: N research summaries
    Merge->>Phase2: all Phase 1 findings
    loop Refinement (up to MAX_ITERATIONS)
        Phase2->>Phase2: produce [DELIVERABLE] goals from ALL findings
        Phase2->>Evaluator: Phase 1 + Phase 2 output
        Evaluator->>Evaluator: score: source quality, claim verification, completeness
        alt PASS (all scores ≥4, 3+ URLs, 1+ quantitative)
            Evaluator->>Composer: exit subgraph
        else FAIL
            Evaluator->>Enhancer: follow-up queries
            Enhancer->>Enhancer: search + synthesize supplement
            Enhancer->>Phase2: augmented findings
            Note over Phase2: regenerates deliverables<br/>with full context
        end
    end
    Composer->>Composer: write report with <cite> tags → markdown links
    Composer-->>User: final report
```

## State Design

```mermaid
classDiagram
    class ResearchState {
        +str topic
        +str research_plan
        +str report_sections
        +bool plan_approved
        +str current_goal
        +list parallel_goals
        +list parallel_findings
        +str section_research_findings
        +Feedback research_evaluation
        +dict sources
        +str final_report_with_citations
        +int iteration_count
        +int max_iterations
    }

    class CitationSource {
        +str short_id
        +str title
        +str url
        +str domain
        +int tier
        +str authority_reason
        +list supported_claims
    }

    class ClaimVerdict {
        +str text
        +int confidence
        +str basis
        +str verdict
    }

    class Feedback {
        +str grade
        +str comment
        +list follow_up_queries
    }

    class SearchQuery {
        +str search_query
    }

    ResearchState *-- Feedback
    ResearchState *-- CitationSource
    CitationSource *-- ClaimVerdict
    Feedback *-- SearchQuery
```

## Parallel Fan-Out (Send API)

```mermaid
flowchart LR
    subgraph Planner
        Goals["Extract [RESEARCH] goals<br/>from approved plan"]
    end

    Planner -->|"Send(current_goal=g)"| R1["parallel_researcher<br/>goal 1"]
    Planner -->|"Send(current_goal=g)"| R2["parallel_researcher<br/>goal 2"]
    Planner -->|"Send(current_goal=g)"| RN["parallel_researcher<br/>goal N"]

    R1 -->|"parallel_findings[0]"| Merge["merge_findings<br/>reducer: operator.add"]
    R2 -->|"parallel_findings[1]"| Merge
    RN -->|"parallel_findings[N]"| Merge

    Merge --> Refine["Refinement Subgraph"]
```

Each `parallel_researcher` runs Phase 1 only for one goal: generate 4-5 search queries → execute all → synthesize summary with [CONFIDENCE:N] tags and [T1/T2/T3] source tiers.

## Refinement Subgraph Detail

```mermaid
stateDiagram-v2
    [*] --> deliverable
    deliverable --> evaluator: Phase 1 + 2 output
    evaluator --> [*]: PASS (all scores ≥4)
    evaluator --> enhancer: FAIL
    enhancer --> deliverable: augmented findings
```

| Node | Role | Key Behavior |
|------|------|-------------|
| **deliverable** | Phase 2 synthesis | Produces [DELIVERABLE] goals from ALL Phase 1 findings. No new searches — synthesis only. Strips previous deliverables on re-run to avoid duplication. |
| **evaluator** | Quality gate | Numeric rubric: source quality (1-5), claim verification (1-5), completeness (1-5). PASS requires all ≥4 + 3+ URL citations + 1+ quantitative finding. |
| **enhancer** | Follow-up research | Runs evaluator's follow_up_queries, synthesizes supplement, appends to findings. Does NOT bypass deliverable — findings feed back through deliverable for full Phase 2 regeneration. |

## Citation System

```mermaid
flowchart LR
    subgraph Sources["Source Lifecycle"]
        EX["1. Extract<br/>markdown links + raw URLs"] --> AT["2. Annotate Tier<br/>domain heuristics"]
        AT --> ST["3. Store in State<br/>sources dict"]
        ST --> CT["4. Composer Cites<br/>&lt;cite source=src-N/&gt;"]
        CT --> RP["5. Replace<br/>markdown links"]
    end

    subgraph Tiers["Source Tiers"]
        T1["Tier 1: arxiv, .gov, .edu<br/>IEEE, official docs"]
        T2["Tier 2: engineering blogs<br/>GitHub, StackOverflow"]
        T3["Tier 3: community, news<br/>vendor content"]
    end
```

## Per-Claim Confidence Scale

| Level | Meaning | Composer Treatment |
|-------|---------|-------------------|
| 5 | Direct measurement, primary source | Stated as fact |
| 4 | Multiple authoritative sources agree | Stated as fact |
| 3 | Reasonable inference | "Evidence suggests..." |
| 2 | Weakly sourced, speculative | "Preliminary data indicates..." |
| 1 | Educated guess | "One possible interpretation..." |

## Search Backend Fallback

```mermaid
flowchart LR
    Q["Search Query"] --> T{"Tavily API<br/>available?"}
    T -->|yes| TR["Tavily Results"]
    T -->|no| S{"SearXNG<br/>available?"}
    S -->|yes| SR["SearXNG Results"]
    S -->|no| DDG["DuckDuckGo<br/>(always available)"]
```

Configured via environment: `TAVILY_API_KEY`, `SEARXNG_URL`. Falls back gracefully — no crash if a backend is unavailable.

## Deployment

```mermaid
flowchart TB
    subgraph Docker["Docker Compose"]
        Agent["deep-research-agent<br/>port 8100<br/>MCP SSE endpoint"]
        SearXNG["deep-research-searxng<br/>port 8080 (internal)<br/>limiter: false"]
        Agent --> SearXNG
    end

    subgraph Host["Host Machine"]
        Hermes["Hermes Agent<br/>MCP client"]
        ExtSearXNG["searxng (shared)<br/>port 8080"]
    end

    Hermes -->|"POST /mcp"| Agent
    Agent -.->|"detects & reuses"| ExtSearXNG
```

`deploy.sh start` auto-detects existing SearXNG on port 8080 (shared with Hermes) or creates a dedicated internal SearXNG with `limiter: false` to avoid 403 bot detection.

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **JSON prompting over `with_structured_output`** | DeepSeek V4 does not support `response_format`. Evaluator uses manual JSON parsing with graceful degradation. |
| **Send API for fan-out** | LangGraph's official pattern for parallel execution. Avoids external process management (old Hermes chat spawning). |
| **Deliverable inside refinement loop** | Enhancer findings must flow through Phase 2 for full regeneration — not shallow append. |
| **Dedicated SearXNG with `limiter: false`** | Shared Hermes SearXNG has rate limiting enabled. Research agent needs unlimited access. |
| **MCP POST JSON-RPC handler** | Hermes probes MCP via POST, not just SSE. Full `initialize` / `tools/list` / `tools/call` dispatch. |
| **Health check ≥30s** | Long research runs exceed default 5s Docker health check. Prevents flapping. |

## File Map

```
deep-research-langgraph/
├── app/
│   ├── agent.py              # StateGraph + subgraph + compilation
│   ├── state.py              # ResearchState TypedDict + Pydantic models
│   ├── config.py             # Env-based configuration dataclass
│   ├── cli.py                # Interactive CLI with plan review
│   ├── mcp_server.py         # MCP SSE/stdio + JSON-RPC POST handler
│   ├── nodes/
│   │   ├── planner.py        # Plan generation + interrupt
│   │   ├── researcher.py     # Phase 1 research + Phase 2 deliverable
│   │   ├── evaluator.py      # Numeric rubric quality evaluation
│   │   ├── enhancer.py       # Follow-up search + synthesis
│   │   └── composer.py       # Report with structured citations
│   └── tools/
│       ├── search.py         # Tavily → SearXNG → DuckDuckGo fallback
│       └── citations.py      # URL extraction, tier annotation, tag replacement
├── tests/
│   └── test_agent.py         # 8 unit tests
├── Dockerfile
├── docker-compose.yml
├── deploy.sh                 # One-command deploy with SearXNG detection
├── searxng-config/
│   └── settings.yml          # limiter: false for internal SearXNG
├── .docker.env.template      # Environment template (keys gitignored)
├── AGENTS.md                 # Quick reference
├── ARCHITECTURE.md           # This document
└── README.md
```
