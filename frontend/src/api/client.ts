import type { RunRequest } from "../types";

// Same-origin in dev thanks to the Vite proxy (see vite.config.ts).
export interface CreatedRun {
  run_id: string;
  stream_url: string;
}

export async function createRun(req: RunRequest): Promise<CreatedRun> {
  const resp = await fetch("/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    throw new Error(`POST /runs failed: ${resp.status} ${await resp.text()}`);
  }
  return resp.json();
}

export function streamUrl(streamPath: string): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}${streamPath}`;
}

export async function submitFeedback(
  runId: string,
  rating: "up" | "down",
  comment?: string,
): Promise<void> {
  await fetch(`/runs/${runId}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rating, comment }),
  });
}
