import type { TraceLine } from "../hooks/useRunSocket";

export function TraceTimeline({ traces }: { traces: TraceLine[] }) {
  if (traces.length === 0) return <p className="muted">Waiting for the run to start…</p>;
  return (
    <ul className="trace">
      {traces.map((t, i) => (
        <li key={i} className={`trace-row ${t.status}`}>
          <span className={`dot ${t.status}`} />
          <span className="trace-node">{t.node}</span>
          <span className="trace-msg">{t.message}</span>
        </li>
      ))}
    </ul>
  );
}
