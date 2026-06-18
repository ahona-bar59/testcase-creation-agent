import { useState } from "react";
import type { Decision, Priority, TestCase, TestType } from "../types";

const DECISIONS: Decision[] = ["CREATE", "UPDATE", "SKIP"];
const TYPES: TestType[] = ["Positive", "Negative", "Edge", "Boundary"];
const PRIORITIES: Priority[] = ["High", "Medium", "Low"];

// HITL Gate #2 — the human edits the actual cases (and may flip a decision),
// then approves. Edits are sent back so the Reviewer grades the edited set.
export function TestCaseEditor({
  cases,
  onApprove,
}: {
  cases: TestCase[];
  onApprove: (choice: string, edited: TestCase[]) => void;
}) {
  const [draft, setDraft] = useState<TestCase[]>(() => structuredClone(cases));
  const [dirty, setDirty] = useState(false);

  function patch(i: number, fields: Partial<TestCase>) {
    setDraft((d) => d.map((tc, idx) => (idx === i ? { ...tc, ...fields } : tc)));
    setDirty(true);
  }
  function patchStep(i: number, s: number, fields: Partial<{ action: string; expected: string }>) {
    setDraft((d) =>
      d.map((tc, idx) =>
        idx === i
          ? { ...tc, steps: tc.steps.map((st) => (st.step === s ? { ...st, ...fields } : st)) }
          : tc,
      ),
    );
    setDirty(true);
  }

  return (
    <div className="modal-backdrop">
      <div className="modal wide">
        <h2>Test review · Gate #2</h2>
        <p className="gate-prompt">
          Review and edit the {draft.length} generated cases. You can change a row’s decision
          (e.g. CREATE → SKIP) or edit any step. Nothing is written until you approve.
        </p>

        <div className="editor-list">
          {draft.map((tc, i) => (
            <div key={tc.id} className="editor-row">
              <div className="editor-head">
                <span className="tc-id">{tc.id}</span>
                <input
                  className="editor-title"
                  value={tc.title}
                  onChange={(e) => patch(i, { title: e.target.value })}
                />
                <select value={tc.decision} onChange={(e) => patch(i, { decision: e.target.value as Decision })}>
                  {DECISIONS.map((d) => (
                    <option key={d}>{d}</option>
                  ))}
                </select>
                <select value={tc.type} onChange={(e) => patch(i, { type: e.target.value as TestType })}>
                  {TYPES.map((t) => (
                    <option key={t}>{t}</option>
                  ))}
                </select>
                <select value={tc.priority} onChange={(e) => patch(i, { priority: e.target.value as Priority })}>
                  {PRIORITIES.map((p) => (
                    <option key={p}>{p}</option>
                  ))}
                </select>
              </div>
              {tc.decision !== "SKIP" && (
                <table className="steps editable">
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
                        <td>
                          <textarea
                            value={st.action}
                            onChange={(e) => patchStep(i, st.step, { action: e.target.value })}
                          />
                        </td>
                        <td>
                          <textarea
                            value={st.expected}
                            onChange={(e) => patchStep(i, st.step, { expected: e.target.value })}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          ))}
        </div>

        <div className="modal-actions">
          <button className="btn primary" onClick={() => onApprove("Approve", draft)}>
            {dirty ? "Approve with edits" : "Approve"}
          </button>
        </div>
      </div>
    </div>
  );
}
