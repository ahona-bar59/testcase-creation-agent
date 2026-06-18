import { NewRun } from "./screens/NewRun";
import { RunView } from "./screens/RunView";
import { useRunSocket } from "./hooks/useRunSocket";

export default function App() {
  const { state, startRun, sendHitl, reset } = useRunSocket();

  return (
    <div className="app">
      <header className="app-header">
        <h1>Test Case Creation Agent</h1>
        <span className="autonomy">L2 · Supervised</span>
      </header>

      {state.status === "idle" ? (
        <NewRun onStart={startRun} />
      ) : (
        <RunView state={state} onRespond={sendHitl} onReset={reset} />
      )}
    </div>
  );
}
