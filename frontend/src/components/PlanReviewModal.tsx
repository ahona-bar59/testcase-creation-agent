import { useState } from "react";
import type { ServerEvent } from "../types";

type PlanGate = Extract<ServerEvent, { type: "hitl" }>;

// HITL Gate #1 — approve the coverage plan, or send a revision back to the planner.
export function PlanReviewModal({
  gate,
  onRespond,
}: {
  gate: PlanGate;
  onRespond: (choice: string) => void;
}) {
  const [freeText, setFreeText] = useState("");
  const plan = gate.plan;

  return (
    <div className="modal-backdrop">
      <div className="modal">
        <h2>Plan review · Gate #1</h2>
        <p className="gate-prompt">{gate.prompt}</p>

        {plan && (
          <div className="plan-stats">
            <Stat n={plan.to_create} label="CREATE" cls="decision-CREATE" />
            <Stat n={plan.to_update} label="UPDATE" cls="decision-UPDATE" />
            <Stat n={plan.to_skip} label="SKIP" cls="decision-SKIP" />
            <Stat n={`${plan.work_avoided_pct}%`} label="work avoided" cls="" />
          </div>
        )}

        {gate.plan_summary && <pre className="plan-summary">{gate.plan_summary}</pre>}

        <div className="modal-actions">
          {gate.options.map((opt) => (
            <button
              key={opt}
              className={opt.toLowerCase().startsWith("yes") ? "btn primary" : "btn"}
              onClick={() => onRespond(opt)}
            >
              {opt}
            </button>
          ))}
        </div>

        <div className="free-text">
          <input
            type="text"
            placeholder="…or type a custom revision (e.g. 'add boundary cases for the 30-min expiry')"
            value={freeText}
            onChange={(e) => setFreeText(e.target.value)}
          />
          <button className="btn" disabled={!freeText.trim()} onClick={() => onRespond(freeText.trim())}>
            Send revision
          </button>
        </div>
      </div>
    </div>
  );
}

function Stat({ n, label, cls }: { n: number | string; label: string; cls: string }) {
  return (
    <div className="plan-stat">
      <span className={`plan-stat-n ${cls}`}>{n}</span>
      <span className="plan-stat-label">{label}</span>
    </div>
  );
}
