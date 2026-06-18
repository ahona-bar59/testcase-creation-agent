# Build Plan — Test Case Creation Agent

> Phase-wise plan to take the agent from a **working offline backend** to a
> **full-stack, production-deployed** system. Organised so each phase has a
> clear goal, tasks, deliverables, and acceptance criteria. Phases are mostly
> sequential, but the **frontend (Phase 3)** and **live LLM (Phase 1)** can
> proceed in parallel because the frontend works against the offline stub.

**Legend:** ✅ done · 🔜 next · ⛔ blocked · ⬜ not started

---

## Phase 0 — Backend agent core ✅ DONE

The LangGraph agent is built, runs END-to-END offline, and is tested.

- ✅ Full graph: `input_guard → planner → plan_review(HITL#1) → executor → test_review(HITL#2) → reviewer → format_output → persist`
- ✅ Deterministic routing, two HITL gates, guarded writes (L2 · Supervised)
- ✅ All tools, Pydantic models, settings slots, event emitter
- ✅ `demo.py` runs START→END; `pytest` → 11 passed
- ✅ Offline-stub mode (no API key needed)

**Acceptance (met):** `python demo.py` → verdict PASS; `python -m pytest -q` → all pass.

---

## Phase 1 — Go live with a real LLM 🔜 (⛔ blocked on API key authorization)

**Goal:** Replace stub generation with real model output. No code changes —
config only.

**Tasks**
- [ ] Obtain Azure OpenAI key + endpoint + deployment name (⛔ awaiting authorization).
- [ ] `Copy-Item .env.example .env`, set `LLM_OFFLINE_STUB=false` + Azure creds + deployment names.
- [ ] `pip install langchain-openai`
- [ ] `python check_llm.py` → confirms connectivity.
- [ ] `python demo.py` → confirm model-generated cases still PASS the gates.

**Fallback while blocked:** the agent supports `LLM_PROVIDER=anthropic` or
`google` with zero code changes. If an Anthropic key is easier to obtain, use it
to unblock this phase early.

**Deliverable:** a live run producing model-authored test cases.
**Acceptance:** `check_llm.py` prints `[OK]`; `demo.py` verdict PASS on a live model.

---

## Phase 2 — Backend service layer (API + WebSocket) ✅ DONE

**Goal:** Expose the agent over HTTP/WebSocket so a UI (or other services) can
trigger runs and answer the two HITL gates in real time.

**Tech:** FastAPI + `uvicorn` + native WebSockets.

**Built**
- ✅ `backend-ai/app/main.py` — FastAPI app + CORS + `/health`.
- ✅ `backend-ai/app/api/schemas.py` — `RunRequest` (mirrors §1.4) + `RunCreated`.
- ✅ `backend-ai/app/api/runs.py` — `POST /runs` + `WS /runs/{run_id}/stream` with the
      thread-bridge driver (sync graph on a worker thread; events streamed via the
      sink; HITL replies bridged back through a `ReplyBridge`).
- ✅ Each gate is sent **exactly once**: the server emits the authoritative `hitl`
      from the interrupt payload and the sink drops the node's duplicate `hitl`
      (which re-fires when the node re-runs on resume).
- ✅ `tests/test_service.py` — 4 tests via `TestClient` (full run, gate-shown-once,
      Gate-#2 edit reflected, unknown run_id). Verified live against `uvicorn` with
      `ws_demo_client.py`.
- [ ] **Remaining for prod:** swap `InMemorySaver` → `PostgresSaver`
      (`CHECKPOINTER=postgres`) so runs survive restarts across the HITL pauses;
      move the `_RUNS` registry to shared storage if running multiple workers.

**Run it**
```powershell
cd backend-ai
uvicorn app.main:app --reload --port 8000   # then open http://127.0.0.1:8000/docs
# in another terminal, from the project root:
python ws_demo_client.py
```

**Event protocol (already emitted by `events.py`):**
```jsonc
// server → client
{ "type": "trace",  "node": "planner", "message": "...", "status": "running|complete" }
{ "type": "genui",  "component": "test-case-table", "data": [ /* TestCase[] */ ] }
{ "type": "hitl",   "prompt": "...", "options": ["...", "..."], "gate": "plan_review" }
{ "type": "done",   "written": { "created": 6, "updated": 2, "skipped": 0 } }

// client → server (answers a hitl pause)
{ "type": "hitl_response", "choice": "Yes, generate the test cases" }
{ "type": "hitl_response", "choice": "Approve", "test_cases_edited": [ /* TestCase[] */ ] }
```

**Deliverable:** `uvicorn app.main:app` serving a run over WebSocket.
**Acceptance:** a CLI/websocket client can drive a full run and answer both gates.

---

## Phase 3 — Frontend ✅ DONE  (built against the offline stub)

**Built** in `frontend/` (React + TypeScript + Vite):
- ✅ `NewRun` form → `POST /runs`; `RunView` with live trace timeline + GenUI panels.
- ✅ `useRunSocket` hook — opens the WebSocket, reduces `trace`/`genui`/`hitl`/`result`/`error`.
- ✅ One component per GenUI: `ScenarioList`, `TestCaseTable`, `CoverageMap`, `ReviewReport`, `TraceTimeline`.
- ✅ HITL surfaces: `PlanReviewModal` (Gate #1 — approve / revise / free-text) and
      `TestCaseEditor` (Gate #2 — edit titles/steps/priority/type, flip decisions, then approve).
- ✅ `ResultView` — verdict banner, persisted counts, review report, full cases.
- ✅ Vite dev-server proxies `/runs` (REST + WS) + `/health` to the backend → same-origin, no CORS.
- ✅ Verified: `npm run build` typechecks + builds; dev-server proxy reaches the live backend `/health`.

**Run it**
```powershell
# backend (Python venv): cd backend-ai ; uvicorn app.main:app --port 8000
cd frontend ; npm install ; npm run dev      # open http://localhost:5173
```

**Original plan (reference):**

**Goal:** A web UI where a tester submits a story, watches live progress, and
**approves/edits at the two HITL gates** — the human-control surface of the L2
contract.

**Tech:** React + TypeScript + Vite. State via React Query / Zustand. WebSocket
client for the live event stream. (Tailwind or MUI for speed.)

### 3.1 Screens / flow
1. **New Run form** — userStory, acceptanceCriteria, projectId, options
   (priority, includeEdgeCases, testTypes). Maps 1:1 to `TestCaseCreationInput` (§1.4).
2. **Run view (live)** — a left **trace timeline** (from `trace` events) + a main
   panel that renders GenUI components as they arrive.
3. **HITL Gate #1 modal** — shows the coverage summary + plan; buttons
   *Approve / Add edge cases / Reduce scope* + free-text. Sends `hitl_response`.
4. **HITL Gate #2 — editable table** — the human edits titles/steps and can flip a
   row's decision (CREATE↔SKIP), then Approve. Sends `test_cases_edited`.
5. **Result view** — final coverage map + review report + persisted counts.

### 3.2 Components (one per GenUI `component`)
| GenUI component | React component | Renders |
|---|---|---|
| `scenario-list` | `<ScenarioList>` | extracted scenarios + suggested type |
| `test-case-table` | `<TestCaseTable>` | `TestCase[]` with decision badges (CREATE/UPDATE/SKIP) |
| `test-case-approval` | `<TestCaseEditor>` | **editable** table for Gate #2 |
| `coverage-map` | `<CoverageMap>` | counts by test type + AC coverage |
| `review-report` | `<ReviewReport>` | grade, verdict, scores, recommendations |

> TypeScript interfaces already exist in the spec (§1.5) — mirror `TestCase`,
> `TestStep`, and the `ReviewReport` shape from `models.py`.

### 3.3 Plumbing
- [ ] `useRunSocket(runId)` hook — opens WS, dispatches events into a reducer.
- [ ] HITL events pause the UI and surface the right modal; the user's reply is
      posted back as `hitl_response`.
- [ ] Thumbs-up / thumbs-down on the final table (feeds Phase 5 improvement data).
- [ ] Reconnect handling (the checkpointer means a run survives a refresh).

**Suggested layout**
```
frontend/
├── index.html
├── package.json
├── vite.config.ts
├── src/
│   ├── main.tsx
│   ├── api/                 # REST + WS clients, event types
│   ├── hooks/useRunSocket.ts
│   ├── components/          # ScenarioList, TestCaseTable, TestCaseEditor,
│   │                        #   CoverageMap, ReviewReport, TraceTimeline
│   ├── screens/             # NewRun, RunView, Result
│   └── store/               # run state reducer
```

**Deliverable:** a UI that runs a story end-to-end with both gates clickable.
**Acceptance:** a tester completes a run, edits a case at Gate #2, and sees it
reflected in the final persisted set — all in the browser, no terminal.

---

## Phase 4 — Real system integrations ✅ DONE (clients implemented; activate at runtime)

Implemented under `…/test_case_creation_langgraph/tools/clients/` — each client has
`available()` + the real call, and tools call it **first**, falling back to the
synthetic stub when unconfigured. So everything is implemented and tested with no
live systems and no API key; the systems "play their role" only at run time.

- ✅ `requirement_store.py` — Neo4j (Cypher) + Azure DevOps (REST/PAT) → `fetch_requirement`.
- ✅ `suite_store.py` — MongoDB text search → `search_existing_tests` / `fetch_test_case`.
- ✅ `vector_index.py` — Azure AI Search + generic HTTP backend → `vector_search_tests`.
- ✅ `test_management.py` — guarded create/update → `create_test_in_system` / `update_test_in_system`.
- ✅ Jira **webhook** endpoint `POST /webhooks/jira` (ADF + plain-text mapping) → registers a run.
- ✅ Connection settings added to `settings.py` (all optional). Tests verify graceful fallback + mapping.

**To activate:** fill the relevant vars in `.env` (see Phase 4 block). No code changes.

**Original plan (reference):**

**Goal:** Replace the graceful stubs in `tools/` with real clients. Each has a
fixed signature, so this is drop-in.

| Tool (file) | Replace stub with | Notes |
|---|---|---|
| `fetch_requirement` (context_tools) | Neo4j / Azure DevOps client | api/webhook triggers |
| `search_existing_tests` (context_tools) | MongoDB text search | existing suite |
| `vector_search_tests` (context_tools) | vector index (e.g. Azure AI Search / pgvector) | semantic dedupe |
| `get_related_context` (context_tools) | docs/glossary store | grounding |
| `create_test_in_system` / `update_test_in_system` (persistence_tools) | test-management API (e.g. Zephyr / ADO Test Plans) | **guarded** writes |

**Tasks**
- [ ] Add a `clients/` package + connection settings to `settings.py`.
- [ ] Wire one integration at a time; keep the stub as the fallback when the
      backing system is unreachable (preserves the "graceful degrade" property).
- [ ] Add a `webhook` endpoint (Phase 2 API) that maps Jira payloads → input.

**Deliverable:** a real story fetched from Jira, deduped against the real suite,
written to the real test-management system after approval.
**Acceptance:** Phase 3 §3.1 of the spec — "one real story flows START→END."

---

## Phase 5 — Deployment & governance ✅ DONE

- ✅ **Feature flag per project** — `app/governance/feature_flags.py` (JSON override → CSV allowlist
  → default). `POST /runs` and the webhook return **403** when a project is disabled (instant rollback).
- ✅ **Version pinning** — `AGENT_VERSION` + `PROMPT_VERSION` in settings, surfaced on `/health` and
  stamped on every logged run + LangSmith trace.
- ✅ **Observability** — `app/governance/observability.py`: structured logging + `run_trace()` wraps
  each run (LangSmith when enabled, no-op otherwise; never breaks a run).
- ✅ **Containerisation** — `backend-ai/Dockerfile`, `frontend/Dockerfile` (+ `nginx.conf` proxy),
  root `docker-compose.yml`, `.dockerignore`. `docker compose up --build` → http://localhost:8080.
- ✅ **CI** — `.github/workflows/ci.yml` runs `pytest` (offline) + the frontend build on every PR.

**Gradual rollout** (operational playbook): 1 pilot tester → 1 QA team (~5%) via `ENABLED_PROJECTS`
→ 1 region → GA by flipping `DEFAULT_PROJECT_ENABLED`. Pin `PROMPT_VERSION`/model for clean rollback.

**Original plan (reference):**

**Goal:** Ship safely with rollback and human control (Phase 4 of the spec).

**Tasks**
- [ ] **Feature flag per project** — flip to manual workflow in seconds on quality drop.
- [ ] **Gradual rollout:** 1 pilot tester → 1 QA team (~5%) → 1 region → GA.
- [ ] **Observability:** enable LangSmith (`LANGCHAIN_TRACING_V2=true` + key);
      structured trace events already emit per node.
- [ ] **Pin** prompt/model versions so rollback is a config change, not a redeploy.
- [ ] Containerise (Dockerfile for backend, static build for frontend) + CI (run `pytest`).

**Acceptance:** a project can be enabled/disabled by flag; a run is fully traceable
in LangSmith; rollback is verified.

---

## Phase 6 — Continuous improvement ✅ DONE (mechanism in place; the loop itself never ends)

- ✅ **Capture** — `app/improvement/feedback.py`: every run is logged (`log_run`); Gate-#2 edits
  (`record_run_signals` — the *diff* of what the human changed) and missed ACs are auto-captured;
  thumbs-up/down via `POST /runs/{run_id}/feedback` and a 👍/👎 control in the result view.
- ✅ **Drift watch** — `app/improvement/metrics.py` + `GET /metrics/summary`: pass rate, Gate-#2 edit
  rate, escalate/best-effort rates, avg completeness/correctness/quality, `work_avoided_pct`, approval %.
- ✅ **Regression set** — `app/improvement/golden_stories.json` + `regression.py`; `scripts/build_regression_set.py`
  harvests FAIL/ESCALATE runs from the log. A test drives every golden story through the agent.
- ⬜ **Expand autonomy** (deliberate, evidence-backed): L2 → Gate #2 notify-only for high-approval
  projects → (L4) direct-persist CREATE rows while still gating UPDATEs. Always behind the feature flag.

---

## Critical path & parallelism

```
Phase 1 (live LLM)  ─┐                         (blocked on key — use Anthropic to unblock)
                     ├─► Phase 2 (API/WS) ─► Phase 4 (integrations) ─► Phase 5 (deploy) ─► Phase 6
Phase 3 (frontend) ─┘   (start NOW vs stub)
```

- **Start the frontend now** — it works against the offline stub, so the API-key
  block does not gate it.
- **Phase 2 is the bridge:** the frontend needs the WebSocket service to talk to.
  A pragmatic order is **2 → 3 in parallel with 1**, then 4 → 5 → 6.

## Immediate next actions
1. ⛔ Chase the Azure OpenAI authorization (or request an Anthropic key to unblock Phase 1).
2. 🔜 Start **Phase 2** (FastAPI + WebSocket wrapper around `run()`).
3. 🔜 Scaffold **Phase 3** frontend against the offline stub in parallel.
