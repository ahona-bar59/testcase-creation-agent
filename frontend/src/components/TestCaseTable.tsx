import type { TestCase } from "../types";

export function TestCaseTable({ cases }: { cases: TestCase[] }) {
  if (cases.length === 0) return null;
  return (
    <div className="card">
      <h3>Test cases ({cases.length})</h3>
      <div className="tc-list">
        {cases.map((tc) => (
          <details key={tc.id} className="tc">
            <summary>
              <span className={`badge decision-${tc.decision}`}>{tc.decision}</span>
              <span className={`badge type-${tc.type}`}>{tc.type}</span>
              <span className={`badge prio-${tc.priority}`}>{tc.priority}</span>
              <span className="tc-id">{tc.id}</span>
              <span className="tc-title">{tc.title}</span>
            </summary>
            <p className="tc-desc">{tc.description}</p>
            {tc.existing_tc_id && (
              <p className="muted">Linked existing case: {tc.existing_tc_id}</p>
            )}
            <table className="steps">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Action</th>
                  <th>Expected</th>
                </tr>
              </thead>
              <tbody>
                {tc.steps.map((st) => (
                  <tr key={st.step}>
                    <td>{st.step}</td>
                    <td>{st.action}</td>
                    <td>{st.expected}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="tc-reason muted">{tc.decision_reason}</p>
          </details>
        ))}
      </div>
    </div>
  );
}
