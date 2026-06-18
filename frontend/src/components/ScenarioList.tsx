import type { Scenario } from "../types";

export function ScenarioList({ scenarios }: { scenarios: Scenario[] }) {
  if (scenarios.length === 0) return null;
  return (
    <div className="card">
      <h3>Extracted scenarios ({scenarios.length})</h3>
      <ul className="scenario-list">
        {scenarios.map((s) => (
          <li key={s.scenario_id}>
            <span className={`badge type-${s.suggested_test_type}`}>{s.suggested_test_type}</span>
            <span className="scenario-text">{s.scenario_text}</span>
            {s.ac_refs.length > 0 && <span className="ac-refs">{s.ac_refs.join(", ")}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
