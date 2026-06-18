import { useState } from "react";
import { submitFeedback } from "../api/client";
import type { RunResult } from "../types";
import { ReviewReport } from "./ReviewReport";
import { TestCaseTable } from "./TestCaseTable";

export function ResultView({ result, runId }: { result: RunResult; runId: string | null }) {
  const [rated, setRated] = useState<"up" | "down" | null>(null);

  function rate(rating: "up" | "down") {
    setRated(rating);
    if (runId) void submitFeedback(runId, rating);
  }

  return (
    <div className="result">
      <div className={`result-banner verdict-${result.verdict}`}>
        <span className="result-verdict">{result.verdict}</span>
        <span>
          Grade {result.grade} · {result.quality_score_pct}% quality · completeness{" "}
          {result.completeness}% · correctness {result.correctness}
        </span>
        {result.is_best_effort && <span className="best-effort">best-effort finish</span>}
        <span className="feedback">
          <button
            className={`thumb ${rated === "up" ? "active" : ""}`}
            onClick={() => rate("up")}
            disabled={rated !== null}
            title="Looks good"
          >
            👍
          </button>
          <button
            className={`thumb ${rated === "down" ? "active" : ""}`}
            onClick={() => rate("down")}
            disabled={rated !== null}
            title="Needs work"
          >
            👎
          </button>
          {rated && <span className="muted">thanks for the feedback</span>}
        </span>
      </div>

      <div className="card">
        <h3>What was persisted</h3>
        <div className="plan-stats">
          <div className="plan-stat">
            <span className="plan-stat-n decision-CREATE">{result.plan.to_create}</span>
            <span className="plan-stat-label">created</span>
          </div>
          <div className="plan-stat">
            <span className="plan-stat-n decision-UPDATE">{result.plan.to_update}</span>
            <span className="plan-stat-label">updated</span>
          </div>
          <div className="plan-stat">
            <span className="plan-stat-n decision-SKIP">{result.plan.to_skip}</span>
            <span className="plan-stat-label">skipped</span>
          </div>
          <div className="plan-stat">
            <span className="plan-stat-n">{result.plan.work_avoided_pct}%</span>
            <span className="plan-stat-label">work avoided</span>
          </div>
        </div>
        {result.errors.length > 0 && (
          <ul className="errors">
            {result.errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        )}
      </div>

      <ReviewReport review={result.review_report} />
      <TestCaseTable cases={result.test_cases} />
    </div>
  );
}
