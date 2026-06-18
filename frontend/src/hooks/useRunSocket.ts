import { useCallback, useRef, useState } from "react";
import { createRun, streamUrl } from "../api/client";
import type {
  CoverageMap,
  ReviewReport,
  RunRequest,
  RunResult,
  Scenario,
  ServerEvent,
  TestCase,
} from "../types";

export type RunStatus =
  | "idle"
  | "connecting"
  | "running"
  | "awaiting_plan"
  | "awaiting_tests"
  | "done"
  | "error";

export interface TraceLine {
  node: string;
  message: string;
  status: "running" | "complete";
}

export interface RunState {
  status: RunStatus;
  runId: string | null;
  traces: TraceLine[];
  scenarios: Scenario[];
  testCases: TestCase[];
  coverage: CoverageMap | null;
  review: ReviewReport | null;
  pendingHitl: Extract<ServerEvent, { type: "hitl" }> | null;
  result: RunResult | null;
  error: string | null;
}

const INITIAL: RunState = {
  status: "idle",
  runId: null,
  traces: [],
  scenarios: [],
  testCases: [],
  coverage: null,
  review: null,
  pendingHitl: null,
  result: null,
  error: null,
};

export function useRunSocket() {
  const [state, setState] = useState<RunState>(INITIAL);
  const wsRef = useRef<WebSocket | null>(null);

  const reset = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    setState(INITIAL);
  }, []);

  const handleEvent = useCallback((ev: ServerEvent) => {
    setState((s) => {
      switch (ev.type) {
        case "trace": {
          // Collapse a node's running→complete into a single updating line.
          const traces = [...s.traces];
          const i = traces.findIndex((t) => t.node === ev.node && t.status === "running");
          const line: TraceLine = { node: ev.node, message: ev.message, status: ev.status };
          if (i >= 0 && ev.status === "complete") traces[i] = line;
          else traces.push(line);
          return { ...s, status: "running", traces };
        }
        case "genui": {
          if (ev.component === "scenario-list")
            return { ...s, scenarios: ev.data as Scenario[] };
          if (ev.component === "test-case-table")
            return { ...s, testCases: ev.data as TestCase[] };
          if (ev.component === "coverage-map")
            return { ...s, coverage: ev.data as CoverageMap };
          if (ev.component === "review-report")
            return { ...s, review: ev.data as ReviewReport };
          return s;
        }
        case "hitl":
          return {
            ...s,
            pendingHitl: ev,
            status: ev.gate === "plan_review" ? "awaiting_plan" : "awaiting_tests",
            // adopt the cases from the gate payload so the editor has the latest
            testCases: ev.test_cases ?? s.testCases,
          };
        case "result":
          return { ...s, result: ev.data, review: ev.data.review_report, status: "done" };
        case "done":
          return s;
        case "error":
          return { ...s, error: ev.message, status: "error" };
        default:
          return s;
      }
    });
  }, []);

  const sendHitl = useCallback((choice: string, testCasesEdited?: TestCase[]) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(
      JSON.stringify({
        type: "hitl_response",
        choice,
        ...(testCasesEdited ? { test_cases_edited: testCasesEdited } : {}),
      }),
    );
    // Clear the gate immediately; the next gate (or result) will arrive.
    setState((s) => ({ ...s, pendingHitl: null, status: "running" }));
  }, []);

  const startRun = useCallback(
    async (req: RunRequest) => {
      reset();
      setState((s) => ({ ...s, status: "connecting" }));
      try {
        const created = await createRun(req);
        const ws = new WebSocket(streamUrl(created.stream_url));
        wsRef.current = ws;
        setState((s) => ({ ...s, status: "running", runId: created.run_id }));
        ws.onmessage = (e) => handleEvent(JSON.parse(e.data) as ServerEvent);
        ws.onerror = () =>
          setState((s) =>
            s.status === "done" ? s : { ...s, error: "WebSocket error", status: "error" },
          );
      } catch (err) {
        setState((s) => ({ ...s, error: String(err), status: "error" }));
      }
    },
    [handleEvent, reset],
  );

  return { state, startRun, sendHitl, reset };
}
