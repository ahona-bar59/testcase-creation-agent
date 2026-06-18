import type { ReviewReport as ReviewReportData } from "../types";

export function ReviewReport({ review }: { review: ReviewReportData }) {
  return (
    <div className="card">
      <h3>
        Review report{" "}
        <span className={`verdict verdict-${review.verdict}`}>{review.verdict}</span>
      </h3>
      <div className="metrics">
        <Metric label="Grade" value={review.grade} />
        <Metric label="Quality" value={`${review.quality_score_pct}%`} />
        <Metric label="Completeness" value={`${review.completeness}%`} />
        <Metric
          label="Correctness"
          value={`${review.correctness}`}
          sub={review.correctness_gate}
          bad={review.correctness_gate === "FAIL"}
        />
      </div>
      {review.recommendations.length > 0 && (
        <>
          <h4>Recommendations</h4>
          <ul className="recs">
            {review.recommendations.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </>
      )}
      {review.escalate_diagnostic && (
        <p className="escalate">⚠ {review.escalate_diagnostic}</p>
      )}
    </div>
  );
}

function Metric({
  label,
  value,
  sub,
  bad,
}: {
  label: string;
  value: string;
  sub?: string;
  bad?: boolean;
}) {
  return (
    <div className="metric">
      <span className="metric-label">{label}</span>
      <span className="metric-value">{value}</span>
      {sub && <span className={`metric-sub ${bad ? "bad" : "good"}`}>{sub}</span>}
    </div>
  );
}
