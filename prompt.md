# Build a LangGraph Deep Research Agent

> **Note:** This is the original design prompt used to generate the agent. For the as-built implementation, see the actual source code in `app/`. Key differences: JSON prompting instead of `with_structured_output` (DeepSeek V4 compatibility), two-pass plan generation instead of `interrupt()`, DELIVERABLE failsafe, circuit breaker, and state pruning.

## Goal

Build a complete, production-ready deep research agent using **LangGraph** that replicates the functionality of the ADK-based `google/adk-samples/python/agents/deep-search` sample. The agent must perform multi-phase research: collaborative planning, parallel web research, iterative refinement with critique loop, and final report synthesis with structured citations.

## Why LangGraph

LangGraph is the purpose-built framework for agent orchestration with:
- **StateGraph** — explicit state management via TypedDict/Pydantic schemas with reducers
- **Subgraphs** — clean composition for the iterative refinement loop
- **Conditional edges** — route based on evaluation results (pass/fail)
- **Persistence** — built-in checkpointing via MemorySaver/SqliteSaver
- **Interrupts** — human-in-the-loop for plan approval
- **LangSmith observability** — trace every node execution for debugging

## Source Materials

### Primary Reference: ADK deep-search agent
Source: https://github.com/google/adk-samples/tree/main/python/agents/deep-search

The ADK agent has these components we must replicate in LangGraph:
- `plan_generator` — LlmAgent that creates/refines research plans with [RESEARCH]/[DELIVERABLE] tags
- `section_planner` — converts plan to a markdown report outline
- `section_researcher` — two-phase executor (Phase A: RESEARCH / Phase B: DELIVERABLE) with web search
- `research_evaluator` — outputs `Feedback` Pydantic model (grade: pass/fail, comment, follow_up_queries)
- `enhanced_search_executor` — executes follow-up queries and merges findings
- `report_composer` — transforms findings + outline into a final cited report
- `collect_research_sources_callback` — extracts web sources and maps URL → short ID (src-1, src-2, ...) with confidence scores
- `citation_replacement_callback` — converts `<cite source="src-1"/>` tags to markdown links
- `EscalationChecker` — custom agent that checks grade and escalates to stop the loop if pass
- `research_pipeline` — SequentialAgent wrapping [section_planner → section_researcher → LoopAgent(iterative_refinement) → report_composer]
- `interactive_planner_agent` — top-level agent that plans with user, then delegates to research_pipeline

### Secondary Reference: Hermes deep-research skill
This is the user's existing deep-research skill implementation (Hermes spawn model). Key patterns from v2.5.0:
- Plan → user approval → parallel children → critique loop → composer
- Structured citations JSON with per-claim confidence (1-5) and basis field
- Source quality tiers (Tier 1: peer-reviewed, Tier 2: practitioner, Tier 3: community)
- Per-claim verdicts: ACCURATE / PARTIALLY ACCURATE / UNSUPPORTED / WRONG

## Project Structure

Create the agent at `/home/jorge/Documents/apps/deep-research-langgraph/` with this structure:

```
deep-research-langgraph/
├── pyproject.toml            # Dependencies: langgraph>=0.4.0, langchain-community, tavily, pydantic
├── app/
│   ├── __init__.py
│   ├── agent.py              # Main graph definition and compilation
│   ├── state.py              # TypedDict/Pydantic state definitions
│   ├── nodes/
│   │   ├── __init__.py
│   │   ├── planner.py        # plan_generator + section_planner logic
│   │   ├── researcher.py     # section_researcher with web search (two-phase)
│   │   ├── evaluator.py      # research_evaluator with Feedback schema
│   │   ├── enhancer.py       # enhanced_search_executor for follow-up queries
│   │   └── composer.py       # report_composer with citation replacement
│   └── tools/
│       ├── __init__.py
│       ├── search.py         # Web search tool wrapper (Tavily or DuckDuckGo)
│       └── citations.py      # Source collection and citation formatting
├── tests/
│   └── test_agent.py
└── README.md
```

## Detailed Implementation Specification

### 1. State Definition (`app/state.py`)

Define the full graph state using TypedDict. All nodes read from and write to this state.

```python
from typing import TypedDict, Optional, Literal, Annotated
from pydantic import BaseModel, Field
import operator

# --- Pydantic Models (ADK-aligned) ---
class SearchQuery(BaseModel):
    search_query: str = Field(description="A highly specific and targeted query for web search.")

class Feedback(BaseModel):
    grade: Literal["pass", "fail"] = Field(description="pass if research is sufficient, fail if needs revision")
    comment: str = Field(description="Detailed evaluation explanation")
    follow_up_queries: list[SearchQuery] | None = Field(default=None, description="Follow-up queries if fail")

class CitationSource(BaseModel):
    short_id: str
    title: str
    url: str
    domain: str
    tier: Literal[1, 2, 3]
    authority_reason: str
    supported_claims: list[dict] = Field(default_factory=list)

class ClaimVerdict(BaseModel):
    text: str
    confidence: Literal[1, 2, 3, 4, 5]
    basis: str
    verdict: Literal["ACCURATE", "PARTIALLY_ACCURATE", "UNSUPPORTED", "WRONG"]

# --- Graph State ---
class ResearchState(TypedDict):
    # Phase 0-1: Planning
    topic: str                                      # User's research topic
    user_feedback: Optional[str]                    # User feedback on plan
    research_plan: Optional[str]                    # Final approved plan
    report_sections: Optional[str]                  # Markdown outline for report
    plan_approved: bool                             # Human approval flag
    
    # Phase 2: Research execution
    section_research_findings: Optional[str]        # Combined research findings
    research_iteration: int                         # Current iteration count
    
    # Evaluation
    research_evaluation: Optional[Feedback]         # Latest evaluation result
    
    # Citation management (ADK-aligned)
    url_to_short_id: Annotated[dict, operator.or_]  # URL → "src-N" mapping
    sources: Annotated[dict, operator.or_]           # short_id → CitationSource
    
    # Phase 3: Report
    final_cited_report: Optional[str]               # Report with <cite> tags
    final_report_with_citations: Optional[str]      # Report with markdown links
    
    # Execution metadata
    messages: list                                   # Conversation history for LLM calls
    iteration_count: int                            # Total refinement iterations
    max_iterations: int                             # Max refinement loops (default: 5)
```

### 2. Graph Architecture (`app/agent.py`)

Build the graph using the pattern:

```
planner_node (plan_generator + section_planner)
    │
    ▼
researcher_node (section_researcher with two-phase execution)
    │
    ▼
[ITERATIVE REFINEMENT SUBGRAPH] ◄──────────┐
    │                                        │
    ▼                                        │
evaluator_node (grade: pass/fail)            │
    │                                        │
    ├── pass ──► composer_node               │
    │                                        │
    └── fail ──► enhancer_node ──────────────┘ (loop back, iteration++)
                    (executes follow-ups)
```

Use a **subgraph** for the iterative refinement loop. The subgraph has its own internal state that extends the parent state with `max_iterations` and `iteration_count`:

```python
from langgraph.graph import StateGraph, END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

# Build the refinement subgraph
def build_refinement_subgraph() -> StateGraph:
    """Subgraph that loops critic → enhancer until pass or max iterations."""
    builder = StateGraph(ResearchState)
    
    builder.add_node("evaluator", research_evaluator_node)
    builder.add_node("enhancer", enhanced_search_executor_node)
    
    def route_after_evaluation(state: ResearchState):
        """Route based on evaluation grade."""
        evaluation = state.get("research_evaluation")
        if evaluation and evaluation.grade == "pass":
            return "end_subgraph"  # Signal to exit subgraph
        if state["iteration_count"] >= state["max_iterations"]:
            return "end_subgraph"  # Max iterations reached
        return "enhancer"  # Keep looping
    
    builder.add_conditional_edges(
        "evaluator",
        route_after_evaluation,
        {
            "enhancer": "enhancer",
            "end_subgraph": END
        }
    )
    
    builder.add_edge("enhancer", "evaluator")  # Increments iteration
    builder.set_entry_point("evaluator")
    
    return builder.compile()

# Build the main graph
def build_research_graph() -> StateGraph:
    builder = StateGraph(ResearchState)
    
    # Add nodes
    builder.add_node("planner", planner_node)
    builder.add_node("researcher", researcher_node)
    builder.add_node("refinement_loop", refinement_subgraph)
    builder.add_node("composer", composer_node)
    
    # Define edges
    builder.set_entry_point("planner")
    builder.add_edge("planner", "researcher")
    builder.add_edge("researcher", "refinement_loop")
    builder.add_edge("refinement_loop", "composer")
    builder.add_edge("composer", END)
    
    return builder.compile(checkpointer=MemorySaver())
```

#### Interrupts for Human-in-the-Loop Plan Approval

Before the researcher runs, use `interrupt` to get user approval:

```python
from langgraph.types import interrupt, Command

def planner_node(state: ResearchState) -> dict:
    """Generate plan and section outline, then interrupt for human approval."""
    # If topic is new, generate the plan
    if not state.get("research_plan"):
        plan = call_plan_generator(state["topic"])
        state["research_plan"] = plan
    
    # Always generate section outline
    if not state.get("report_sections"):
        sections = call_section_planner(state["research_plan"])
        state["report_sections"] = sections
    
    # Interrupt for human approval (unless already approved)
    if not state.get("plan_approved"):
        interrupt({
            "question": "Review the research plan below. Approve to proceed or provide feedback.",
            "research_plan": state["research_plan"],
            "report_sections": state["report_sections"]
        })
        # After interrupt resumes, check if plan_approved was set
        if not state.get("plan_approved"):
            # User provided feedback
            pass  # Will regenerate in next invocation
    
    return state
```

### 3. Node Implementations

#### 3a. Planner Node (`app/nodes/planner.py`)

Two LLM calls in sequence:

1. **Plan Generator** — Takes the topic, generates a research plan with 5 action-oriented goals. Each goal is prefixed with `[RESEARCH]` or `[DELIVERABLE]`. If the plan already exists and `user_feedback` is provided, refine with tags: `[MODIFIED]`, `[NEW]`, `[IMPLIED]`.

```
LLM System Prompt (Plan Generator):
"You are a research strategist. Create a 5-point action-oriented research plan.
Prefix each goal with either [RESEARCH] or [DELIVERABLE].
RESEARCH goals start with verbs like 'Analyze', 'Identify', 'Investigate'.
DELIVERABLE goals describe synthesis/output artifacts.
If adding implied deliverables, prefix with [DELIVERABLE][IMPLIED].
Current date: {datetime.now()}"
```

2. **Section Planner** — Takes the plan, produces a markdown report outline with 4-6 sections.

```
LLM System Prompt (Section Planner):
"You are an expert report architect. Create a markdown outline with 4-6 distinct sections.
Use any markdown format. Do not include a References or Sources section."
```

#### 3b. Researcher Node (`app/nodes/researcher.py`)

Two-phase executor (ADK-aligned):

```
LLM System Prompt (Section Researcher):
"You are a research and synthesis agent. You execute the research plan with absolute fidelity.

Phase 1 - RESEARCH tasks:
- For each [RESEARCH] goal: generate 4-5 search queries, execute all via web_search, synthesize summaries.
- Store summaries internally.

Phase 2 - DELIVERABLE tasks:
- Only start after ALL RESEARCH goals complete.
- For each [DELIVERABLE] goal: produce the exact artifact (table, summary, report).
- Use only Phase 1 summaries. Do not perform new searches."
```

**Web search tool**: Use `TavilySearchResults` (recommended for production) or `DuckDuckGoSearchRun`. Configure via env vars:
- `TAVILY_API_KEY` for Tavily
- Or default to DuckDuckGo

**Source collection**: After the researcher generates findings, run the source collection logic:

```python
from app.tools.citations import collect_research_sources

def collect_research_sources_node(state: ResearchState) -> dict:
    """Post-processing: extract grounding sources from the LLM response."""
    # This runs AFTER the researcher node and collects URL→short_id mapping
    # Parse the LLM response for URLs, extract titles, domains
    # Build structured citations with confidence scores
    new_sources, new_url_map = extract_sources_from_content(
        state["section_research_findings"]
    )
    return {
        "sources": {**state.get("sources", {}), **new_sources},
        "url_to_short_id": {**state.get("url_to_short_id", {}), **new_url_map}
    }
```

#### 3c. Research Evaluator Node (`app/nodes/evaluator.py`)

Uses **JSON prompting** instead of `with_structured_output` for model compatibility.

**Why JSON prompting:** DeepSeek V4 and many open-source models don't support `response_format` / `with_structured_output`. JSON prompting works universally.

```python
import json
import re

def _parse_json(text: str) -> dict:
    """Extract JSON from LLM output with graceful fallback."""
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    raw = m.group(1) if m else text.strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start:end + 1]
    return json.loads(raw)

def research_evaluator_node(state: ResearchState) -> dict:
    """Critique the research findings with a numeric rubric."""
    llm = get_llm()  # plain LLM, no structured output
    
    system = """You are a meticulous quality assurance analyst.
Evaluate the research findings and return ONLY a JSON object:

{
  "grade": "pass" or "fail",
  "source_quality": 1-5,
  "claim_verification": 1-5,
  "completeness": 1-5,
  "comment": "detailed evaluation with specific gaps",
  "follow_up_queries": [{"search_query": "specific query"}]
}

STRICT RUBRIC:
- PASS requires: ALL scores >= 4, at least 3 unique URL citations,
  at least 1 quantitative finding (number, percentage, benchmark)
- FAIL otherwise — be specific about what's missing"""
    
    response = llm.invoke([
        SystemMessage(content=system),
        HumanMessage(content=f"Topic: {state['topic']}\nFindings:\n{state['section_research_findings']}")
    ])
    
    try:
        data = _parse_json(response.content)
    except (json.JSONDecodeError, ValueError):
        logger.warning("JSON parse failure, using fallback")
        data = {"grade": "fail", "comment": "Parse error"}
    
    return {"research_evaluation": data}
```

**Fallback pattern:** If JSON parsing fails, default to FAIL with a parse error comment — the enhancer will run follow-up queries and the evaluator gets another chance. Never crash the pipeline on parse failure.

#### 3d. Enhanced Search Executor Node (`app/nodes/enhancer.py`)

When evaluator grades FAIL, this node runs:

```python
def enhanced_search_executor_node(state: ResearchState) -> dict:
    """Execute follow-up queries and merge findings with existing research."""
    evaluation = state["research_evaluation"]
    follow_ups = evaluation.follow_up_queries or []
    
    # Execute all follow-up queries via web search
    search_tool = get_search_tool()
    new_findings = []
    for query in follow_ups:
        results = search_tool.invoke({"query": query.search_query})
        new_findings.append(format_search_results(query.search_query, results))
    
    # Merge new findings with existing research
    combined = state["section_research_findings"]
    combined += "\n\n## Additional Research (from refinement)\n"
    combined += "\n\n".join(new_findings)
    
    return {
        "section_research_findings": combined,
        "iteration_count": state.get("iteration_count", 0) + 1,
        "sources": merged_sources  # Also collect new sources
    }
```

#### 3e. Composer Node (`app/nodes/composer.py`)

Final synthesis with citation replacement (ADK-aligned):

```python
def composer_node(state: ResearchState) -> dict:
    """Transform research findings and section outline into a final cited report."""
    
    # First pass: LLM writes the report with <cite source="src-N"/> tags
    llm = get_chat_model()
    
    report = llm.invoke([
        SystemMessage(content=f"""
        Transform the provided data into a polished, professional, meticulously cited research report.
        
        CRITICAL CITATION SYSTEM:
        To cite a source, insert: <cite source="src-ID_NUMBER" />
        
        Inputs:
        - Research Plan: {state['research_plan']}
        - Research Findings: {state['section_research_findings']}
        - Citation Sources: {json.dumps(state.get('sources', {}))}
        - Report Structure: {state['report_sections']}
        
        Follow the report structure exactly. No References or Sources section.
        """),
        HumanMessage(content=f"Findings: {state['section_research_findings']}")
    ])
    
    # Second pass: Replace <cite> tags with markdown links
    def citation_replacer(match: re.Match) -> str:
        short_id = match.group(1)
        source_info = state.get("sources", {}).get(short_id)
        if not source_info:
            return ""
        display_text = source_info.get("title", source_info.get("domain", short_id))
        return f" [{display_text}]({source_info['url']})"
    
    final_report = re.sub(
        r'<cite\s+source\s*=\s*[\"\']?\s*(src-\d+)\s*[\"\']?\s*/>',
        citation_replacer,
        report.content
    )
    
    return {
        "final_cited_report": report,
        "final_report_with_citations": final_report
    }
```

### 4. Tools (`app/tools/`)

#### Search Tool (`app/tools/search.py`)

Wrap TavilySearchResults or DuckDuckGoSearchRun. Support both with fallback:

```python
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_community.tools.tavily_search import TavilySearchResults

def get_search_tool():
    """Factory: return TavilySearchResults if API key set, else DuckDuckGo."""
    if os.getenv("TAVILY_API_KEY"):
        return TavilySearchResults(max_results=5)
    return DuckDuckGoSearchRun()
```

#### Citation Manager (`app/tools/citations.py`)

Replicate the ADK `collect_research_sources_callback` functionality:

```python
def collect_research_sources(event, state: dict) -> dict:
    """Extract web sources from an agent event's grounding metadata.
    
    ADK pattern: Collect URLs, titles, domains from grounding_chunks,
    map URL → short_id (src-N), and attach supported_claims with confidence scores.
    
    Returns updated state with new sources added.
    """
    # Parse the event content for URLs cited in the LLM response
    # Build url_to_short_id and sources dicts
    # Each source has: short_id, title, url, domain, supported_claims[]
    # Each claim has: text_segment, confidence
    pass
```

### 5. Environment Configuration

The agent needs these env vars:

```python
# app/config.py
from dataclasses import dataclass
import os

@dataclass
class ResearchConfig:
    """ADK-aligned configuration."""
    worker_model: str = os.getenv("WORKER_MODEL", "gpt-4o")
    critic_model: str = os.getenv("CRITIC_MODEL", "gpt-4o")  # Could use a stronger model
    max_search_iterations: int = int(os.getenv("MAX_SEARCH_ITERATIONS", "5"))
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")
    langchain_api_key: str = os.getenv("LANGCHAIN_API_KEY", "")
    
config = ResearchConfig()
```

### 6. LLM Integration

Use LangChain's Chat Model interface. The model must support tool calling (for structured output) and streaming:

```python
from langchain.chat_models import init_chat_model

def get_chat_model(model_name: str | None = None):
    """Initialize a chat model supporting tool calling."""
    return init_chat_model(
        model_name or config.worker_model,
        temperature=0.1,
    )
```

### 7. Testing

```python
# tests/test_agent.py
from app.agent import build_research_graph

def test_full_research_pipeline():
    graph = build_research_graph()
    
    # Initial state
    initial = {
        "topic": "Recent advances in autonomous AI agents (2025-2026)",
        "plan_approved": True,  # Skip human-in-the-loop for testing
        "messages": [],
        "iteration_count": 0,
        "max_iterations": 3,
        "url_to_short_id": {},
        "sources": {},
        "research_plan": None,
        "report_sections": None,
        "section_research_findings": None,
        "research_evaluation": None,
        "final_cited_report": None,
        "final_report_with_citations": None,
        "user_feedback": None
    }
    
    # Run with thread_id for checkpointing
    config = {"configurable": {"thread_id": "test-1"}}
    result = graph.invoke(initial, config)
    
    assert result["final_report_with_citations"] is not None
    assert len(result["final_report_with_citations"]) > 500
    # Verify citations are present
    assert "http" in result["final_report_with_citations"]
```

### 8. Entry Points

#### CLI Entry

```python
# app/cli.py
def run_research(topic: str):
    """Run deep research from the command line."""
    graph = build_research_graph()
    
    state = {
        "topic": topic,
        "plan_approved": False,
        "messages": [],
        "iteration_count": 0,
        "max_iterations": 5,
        "url_to_short_id": {},
        "sources": {},
    }
    
    thread_config = {"configurable": {"thread_id": f"research-{int(time.time())}"}}
    
    # First run: plan generation
    for event in graph.stream(state, thread_config):
        # Handle interrupts for plan approval
        if isinstance(event, dict) and "interrupt" in event:
            print("\n=== RESEARCH PLAN ===")
            print(event["interrupt"]["research_plan"])
            print("\n=== REPORT SECTIONS ===")
            print(event["interrupt"]["report_sections"])
            approval = input("\nApprove plan? (yes/feedback): ")
            if approval.lower() == "yes":
                state["plan_approved"] = True
            else:
                state["user_feedback"] = approval
            graph.update_state(thread_config, state)
        
        # Stream intermediate results
        for node_name, node_output in (event.items() 
                                        if isinstance(event, dict) 
                                        else [("", event)]):
            if node_name == "researcher":
                print(f"\n[Research complete: findings gathered]")
            elif node_name == "evaluator":
                eval_result = node_output.get("research_evaluation")
                if eval_result:
                    print(f"\n[Evaluation: {eval_result.grade.upper()}]")
                    print(eval_result.comment)
    
    final_state = graph.get_state(thread_config)
    print("\n\n" + "="*60)
    print("FINAL REPORT")
    print("="*60)
    print(final_state.values["final_report_with_citations"])
    
    # Save report
    with open(f"report-{int(time.time())}.md", "w") as f:
        f.write(final_state.values["final_report_with_citations"])
```

#### Interactive LangGraph Studio

The graph can also be loaded in LangGraph Studio for visual debugging and human-in-the-loop approval workflows.

## Key Design Decisions

1. **StateGraph over Functional API** — The Graph API provides explicit node/edge control needed for conditional routing (pass/fail evaluation), whereas Functional API is better for linear workflows. The conditional edge from evaluator requires Graph API.

2. **Subgraph for refinement loop** — The iterative critic → enhancer loop is a natural subgraph boundary. It isolates the loop logic (max iterations, escalation check) from the main pipeline. This mirrors ADK's `LoopAgent` pattern.

3. **JSON prompting over `with_structured_output`** — DeepSeek V4 does not support `response_format`. The evaluator uses JSON prompting with manual parsing and graceful fallback (defaulting to FAIL on parse errors). This works universally across all model providers without requiring proprietary features.

4. **Interrupts for plan approval** — LangGraph's built-in `interrupt()` is cleaner than ADK's manual user input handling. It provides checkpoint-based persistence: the graph state is saved, the interrupt fires, and the user can resume later with `Command(resume=...)`.

5. **Source collection as a post-processing node** — ADK uses `after_agent_callback` to collect sources after every LLM call. In LangGraph, this is a separate node that runs after research and after enhancement. The state's `operator.or_` reducer merges sources across invocations.

6. **No strict need for the `EscalationChecker` custom agent** — The conditional edge function in LangGraph replaces this entirely. Simply: if grade is 'pass' OR iteration >= max, exit subgraph; else loop.

## Quality Requirements

The final agent must:

1. **Handle real web searches** — Not just return hardcoded results. Integrate with Tavily or DuckDuckGo.
2. **Produce structured citations** — Every claim must link to a source. Use the `<cite source="src-N"/>` format during composition, then convert to markdown.
3. **Handle the full workflow** — Plan → Research → Evaluate → (loop) → Compose. No shortcuts.
4. **Support human-in-the-loop** — The plan must be user-approved before research starts.
5. **Gracefully degrade** — If a search fails, log it and continue with available results.
6. **Produce output as a markdown file** — Saved to disk with timestamp.
7. **Pass basic tests** — The test file should verify the graph compiles and runs end-to-end.

## What to Do First

1. Read the ADK example code at the GitHub URL above to understand the exact agent structure.
2. Read the current LangGraph Graph API docs at `https://docs.langchain.com/oss/python/langgraph/graph-api` for the latest API patterns.
3. Install dependencies with pip or uv.
4. Build state definitions in `app/state.py`.
5. Implement each node in `app/nodes/`.
6. Wire up the graph in `app/agent.py`.
7. Test with `python -m pytest tests/`.
8. Run a real research query.
