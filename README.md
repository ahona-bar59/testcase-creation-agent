# Test Case Creation Agent

> Turn a user story + acceptance criteria into **reviewed, coverage-aware test cases** — and ask a human before writing anything into the test system.

| | |
|---|---|
| **Agent ID** | `test-case-creation-langgraph` |
| **Framework** | LangGraph `StateGraph` + three `create_react_agent` workers |
| **Autonomy** | **L2 · Supervised** — deterministic routing + two blocking HITL gates (~70% human control) |
| **Default LLM provider** | Azure OpenAI (swappable to Anthropic / Gemini from settings) |
| **Triggers** | `manual` · `api` · `webhook` |
| **Output** | `test-case-table` · `coverage-map` · `review-report` (GenUI) |

This repository is a full, runnable implementation of the agent specified in
`test-case-creation-agent (updated).md`. It runs **end to end with no API keys**
in an offline-stub mode (see [Quick start](#quick-start)), and swaps to live
models with a single config change.

---

## Why this agent exists (Discovery)

Writing test cases by hand is slow (1–3 hrs per story), leaks edge-case coverage
under time pressure, and produces duplicates because searching the existing
suite is tedious. The work is language-heavy and pattern-driven — a good fit for
an LLM — but the *judgement* of whether a case is correct stays with a human.

Crucially, the agent does **not** automate the broken habit of "write everything
from scratch." Its first job is to **search the existing suite and decide
CREATE / UPDATE / SKIP per scenario**, so the process gets *better*, not just faster.

---

## Architecture

### The graph

```
START
  │
  ▼
input_guard ──► planner ──► plan_review (HITL #1)
                              │ approve            │ revise
                              ▼                    └──► back to planner
                          executor
                              │ retry_count == 0        │ retry_count > 0
                              ▼                          │
                       test_review (HITL #2)             │
                              │                          │
                              ▼                          ▼
                           reviewer ◄────────────────────┘
                              │
              ┌───────────────┼───────────────────┐
        PASS/ESCALATE     FAIL & <2 retries     FAIL & ≥2 retries
              │               │                     │
              ▼               ▼ (self-correct)      ▼ (best-effort)
        format_output ◄──── executor            format_output
              │
              ▼
           persist (guarded writes)
              │
              ▼
            END
```

- **Amber** gates (`plan_review`, `test_review`) are human-in-the-loop pauses via `interrupt()`.
- **Red** node (`persist`) is the only place that writes to the test system.
- **Blue** node (`input_guard`) is the inbound guardrail.
- **Routing is deterministic** — there is no LLM coordinator (`routing.py`). This is what makes the agent L2 · Supervised and its control flow testable.

### The three workers (the "brain")

Each worker resolves its model from a per-worker **settings slot** via the shared
`build_llm()` factory. Provider and temperature travel inside the slot, so node
code never names a provider.

| Worker | Slot | Tuning | Job |
|---|---|---|---|
| Planner | `settings.llm_planner` | low temp | scenarios, coverage decisions, plan |
| Executor | `settings.llm_executor` | higher temp | writes step-based test cases |
| Reviewer | `settings.llm_reviewer` | lowest temp | the two quality gates |

`react.py` builds these as `create_react_agent` workers for the live path. For
reliability and offline/test execution, the nodes in `nodes.py` orchestrate the
documented tool sequence deterministically (the same reasoning the spec applies
to the executor "mega-tool": a single predictable call beats a fragile loop).

### The memory

The whole run lives in one typed `TestCaseCreationState` (`state.py`). A
**checkpointer** keyed by `run_id` (== `thread_id`) persists it across the two
HITL pauses — `InMemorySaver` in dev, `PostgresSaver` in prod (chosen by
`settings.checkpointer`).

### The tools (`tools/`)

| Group | Module | Tools |
|---|---|---|
| Context retrieval | `context_tools.py` | `fetch_requirement`, `search_existing_tests`, `vector_search_tests`, `get_related_context`, `fetch_test_case`, `get_test_template` |
| Coverage analysis | `coverage_tools.py` | `extract_scenarios`, `compare_coverage` (BATCH: SKIP ≥90, UPDATE 30–89, CREATE <30) |
| Requirement analysis | `analysis_tools.py` | `analyze_requirement` |
| Generation | `generation_tools.py` | `generate_test_plan`, `generate_test_case`, `update_test_case`, `execute_plan_actions` (mega-tool) |
| Persistence (**guarded**) | `persistence_tools.py` | `create_test_in_system`, `update_test_in_system` |
| Review | `review_tools.py` | `validate_completeness`, `check_data_coverage`, `check_correctness`, `generate_review_report`, `analyze_failures` |

External systems (Neo4j/ADO requirement store, MongoDB suite, vector index) are
wrapped behind these signatures and degrade gracefully to synthetic-but-structured
data when the backing system is absent — so the graph always runs.

### The nodes (`nodes.py`)

| Node | Role |
|---|---|
| `input_guard` | mask PII · neutralise prompt-injection · enforce 8000-token limit (no LLM) |
| `planner` | the 6-step ReAct sequence → decision-tagged `test_plan`; emits `scenario-list` |
| `plan_review` | **HITL #1** — approve plan or send a revision back to the planner |
| `executor` | one `execute_plan_actions` call (CREATE/UPDATE/SKIP); increments `retry_count` on self-correction |
| `test_review` | **HITL #2** — editable approval table; edits are graded by the reviewer |
| `reviewer` | Gate 1 completeness + Gate 2 correctness (hard gate <80 → FAIL); `analyze_failures` on FAIL |
| `format_output` | schema-validate `TestCase[]`, strip leaked PII, emit final GenUI |
| `persist` | **guarded** writes; routes by decision; failures surface but never abort |

---

## The L2 · Supervised contract

A human approves **every write** to the test system, enforced by two gates:

1. **Gate #1 (plan)** — the human approves *what* will be created/updated/skipped before any drafting.
2. **Gate #2 (test cases)** — the human reviews and may **edit** the actual cases before the reviewer and before anything is persisted.

Self-correction retries stay *inside* the approved boundary and skip the human
gate (`route_after_executor`), so the human is never re-asked — but they also
never silently introduce new writes. The `persist` node writes only the approved set.

---

## Guardrails

| Guardrail | Where | Behaviour |
|---|---|---|
| `pii-detection` | `input_guard` | mask names/emails before the planner sees the story |
| `prompt-injection` | `input_guard` | neutralise injection patterns |
| `input-length-limit` | `input_guard` | truncate above 8000 tokens |
| `plan-approval` | `plan_review` | human approves plan before drafting |
| `test-case-approval` | `test_review` | human reviews/edits before persistence |
| `write-confirmation` | `persist` | only approved rows are written; SKIP never writes |
| `self-correction-budget` | `route_after_review` | `retry_count < 2`, else best-effort finish |
| `output-schema-validation` | `format_output` | validate `TestCase[]` before emit |
| `output-pii-redaction` | `format_output` | strip PII that leaked into fields |

---

## Quick start

```bash
# 1. Install (core deps are enough for the offline demo)
pip install -r requirements.txt

# 2. Run the full graph END-to-END with no API keys (offline stub mode)
python demo.py

# 3. Run the test suite (node · tool · routing · graph · HITL · chaos)
pip install pytest pytest-asyncio
pytest -q
```

`demo.py` seeds an existing suite, runs a password-reset story through the whole
graph, auto-approves both HITL gates, and prints the event stream + final verdict.

### Going live (Gemini — default)

`.env` is preconfigured for **Google Gemini**. Just paste your key
(https://aistudio.google.com/app/apikey):

```dotenv
LLM_PROVIDER=google
GOOGLE_API_KEY=your-gemini-key
LLM_OFFLINE_STUB=false
LLM_PLANNER_MODEL=gemini-2.0-flash   # executor/reviewer too
```

With an empty key it safely falls back to the offline stub (runs as before);
with a key it goes live. Validate with `python check_llm.py`.

**Other providers** — change `LLM_PROVIDER` and fill that key; model names
auto-default per provider, so this is the only change:

```dotenv
# LLM_PROVIDER=anthropic   + ANTHROPIC_API_KEY=...
# LLM_PROVIDER=azure_openai + AZURE_OPENAI_API_KEY=... + AZURE_OPENAI_ENDPOINT=...
```

No node or tool code changes — provider/temperature live in the settings slots.

### Embedding in a service

```python
from app.agents.test_case_creation_langgraph import run

final = run(
    payload={"userStory": "...", "acceptanceCriteria": "...", "projectId": "P1"},
    responder=my_hitl_responder,   # answers each interrupt (round-trips to the UI)
    sink=my_ws_event_sink,         # receives trace / genui / hitl / done events
)
```

---

## Input / Output contracts

**Input** (`build_initial_state` maps this onto state):

```jsonc
{
  "userStory": "As a user, I want ...",
  "acceptanceCriteria": "AC-1: ...\nAC-2: ...",  // optional
  "projectId": "P1",
  "jiraStoryId": "PROJ-123",                      // present on api/webhook
  "trigger_type": "manual",                        // manual | api | webhook
  "options": { "priority": "High", "includeEdgeCases": true }
}
```

**Output** — `TestCase[]` (see `models.py`) plus a `ReviewReport` and a coverage map.

---

## Success metrics (how we know it works)

| Metric | Target |
|---|---|
| Time to draft a suite for one story | ≤ 5 min (from 1–3 hrs) |
| AC coverage (Gate 1) | 100% |
| Correctness score (Gate 2, hard gate) | ≥ 80 |
| Duplicate work avoided | `work_avoided_pct > 0` on stories with existing coverage |
| Human approval rate at Gate #2 | ≥ 80% |

---

## Project layout

```
test-case-creation-agent/
├── README.md                 ← this file
├── requirements.txt
├── pyproject.toml
├── .env.example
├── demo.py                   ← end-to-end offline demo
├── tests/
│   └── test_agent.py         ← node · tool · routing · graph · HITL · chaos
└── backend-ai/app/agents/test_case_creation_langgraph/
    ├── __init__.py           ← public entrypoints
    ├── agent.py              ← build_workflow() · build_initial_state() · run()
    ├── settings.py           ← Settings + per-worker LLMSlot (build_llm input)
    ├── state.py              ← TestCaseCreationState TypedDict
    ├── models.py             ← Pydantic data models (Appendix A)
    ├── routing.py            ← deterministic conditional edges
    ├── prompts.py            ← one system prompt per worker / LLM tool
    ├── nodes.py              ← the 8 node functions
    ├── react.py              ← create_react_agent worker builders (live path)
    ├── events.py             ← trace / genui / hitl event emitter
    └── tools/
        ├── __init__.py       ← tool catalogue
        ├── shared.py         ← build_llm factory · workspace cache · JSON helpers
        ├── context_tools.py
        ├── coverage_tools.py
        ├── analysis_tools.py
        ├── generation_tools.py
        ├── persistence_tools.py   (guarded)
        └── review_tools.py
```

> **Note on additions to the spec's file list:** `settings.py`, `react.py`, and
> `events.py` are supporting modules the spec references in prose (the settings
> slots, the `create_react_agent` workers, and the WebSocket event stream) but
> did not enumerate in Appendix B. They are kept small and single-purpose.

---

## Continuous improvement (Phase 5)

- **Watch for drift** monthly: AC-coverage & correctness distributions, Gate-#2
  approval rate (a falling rate is an early signal), and `work_avoided_pct`
  (a sudden drop can mean the existing-test search is failing).
- **Feed experience back**: every Gate-#2 edit, thumbs-down, and missed AC from
  `analyze_failures` is training data for the next prompt version and a regression set.
- **Expand autonomy deliberately**: L2 → collapse Gate #2 to notify-only for
  high-approval projects → (L4) direct persistence of CREATE rows while still
  gating UPDATEs. Always behind the per-project feature flag, always reversible.
```
