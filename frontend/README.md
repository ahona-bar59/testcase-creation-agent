# Frontend — Test Case Creation Agent

React + TypeScript + Vite UI for the agent. It drives a run over the Phase 2
WebSocket service and surfaces the two **human-in-the-loop gates** — the human
approves the plan (Gate #1) and reviews/edits the generated cases (Gate #2).

## Prerequisites

The backend (Phase 2) must be running:

```powershell
# from the repo root, in your Python venv
cd backend-ai
uvicorn app.main:app --port 8000
```

No API key needed — the backend runs in offline-stub mode by default.

## Run the frontend

```powershell
cd frontend
npm install
npm run dev
```

Open the URL Vite prints (default http://localhost:5173). The dev server proxies
`/runs` (REST + WebSocket) and `/health` to the backend on :8000, so everything
is same-origin — no CORS setup needed. If your backend is elsewhere, set
`VITE_BACKEND` (see `.env.example`).

## What you'll see

1. **New run form** — story, acceptance criteria, project, options (prefilled with a sample).
2. **Run view** — a live **trace timeline** on the left; scenarios, coverage map,
   and review report stream into the main panel.
3. **Gate #1 modal** — approve the coverage plan, pick "add edge cases" / "reduce
   scope", or type a free-text revision (which loops back to the planner).
4. **Gate #2 editor** — edit titles, steps, priority/type, or flip a row's
   decision (CREATE↔SKIP), then approve. Edits are graded by the reviewer.
5. **Result view** — verdict banner, what was persisted, review report, full cases.

## How it maps to the backend

| Backend event | Handled by |
|---|---|
| `trace` | `TraceTimeline` (sidebar) |
| `genui: scenario-list` | `ScenarioList` |
| `genui: test-case-table` | `TestCaseTable` |
| `genui: coverage-map` | `CoverageMap` |
| `genui: review-report` | `ReviewReport` |
| `hitl: plan_review` | `PlanReviewModal` → sends `hitl_response` |
| `hitl: test_review` | `TestCaseEditor` → sends `hitl_response` + `test_cases_edited` |
| `result` | `ResultView` |

All event/domain types live in `src/types.ts`; the socket lifecycle is in
`src/hooks/useRunSocket.ts`.

## Scripts

- `npm run dev` — dev server with HMR
- `npm run build` — typecheck + production build to `dist/`
- `npm run typecheck` — types only
