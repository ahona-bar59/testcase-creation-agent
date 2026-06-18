import { CoverageMap } from "../components/CoverageMap";
import { PlanReviewModal } from "../components/PlanReviewModal";
import { ResultView } from "../components/ResultView";
import { ReviewReport } from "../components/ReviewReport";
import { ScenarioList } from "../components/ScenarioList";
import { TestCaseEditor } from "../components/TestCaseEditor";
import { TestCaseTable } from "../components/TestCaseTable";
import { TraceTimeline } from "../components/TraceTimeline";
import type { RunState } from "../hooks/useRunSocket";
import type { TestCase } from "../types";

export function RunView({
  state,
  onRespond,
  onReset,
}: {
  state: RunState;
  onRespond: (choice: string, edited?: TestCase[]) => void;
  onReset: () => void;
}) {
  const { status, pendingHitl } = state;

  return (
    <div className="run-view">
      <aside className="sidebar">
        <div className="status-line">
          <StatusPill status={status} />
          {state.runId && <span className="run-id">{state.runId}</span>}
        </div>
        <h3>Progress</h3>
        <TraceTimeline traces={state.traces} />
        <button className="btn ghost" onClick={onReset}>
          ← New run
        </button>
      </aside>

      <main className="stage">
        {state.error && <div className="error-banner">Error: {state.error}</div>}

        {state.result ? (
          <ResultView result={state.result} runId={state.runId} />
        ) : (
          <>
            <ScenarioList scenarios={state.scenarios} />
            {state.coverage && <CoverageMap coverage={state.coverage} />}
            {state.testCases.length > 0 && status !== "awaiting_tests" && (
              <TestCaseTable cases={state.testCases} />
            )}
            {state.review && <ReviewReport review={state.review} />}
          </>
        )}
      </main>

      {/* HITL gates render as blocking modals */}
      {pendingHitl?.gate === "plan_review" && (
        <PlanReviewModal gate={pendingHitl} onRespond={(c) => onRespond(c)} />
      )}
      {pendingHitl?.gate === "test_review" && (
        <TestCaseEditor
          cases={pendingHitl.test_cases ?? state.testCases}
          onApprove={(c, edited) => onRespond(c, edited)}
        />
      )}
    </div>
  );
}

function StatusPill({ status }: { status: RunState["status"] }) {
  const label: Record<RunState["status"], string> = {
    idle: "Idle",
    connecting: "Connecting…",
    running: "Running…",
    awaiting_plan: "Awaiting plan approval",
    awaiting_tests: "Awaiting test review",
    done: "Done",
    error: "Error",
  };
  return <span className={`status-pill ${status}`}>{label[status]}</span>;
}
