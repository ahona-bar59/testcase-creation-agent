// Domain + event types — mirror backend models.py and the WS event protocol.

export type Priority = "High" | "Medium" | "Low";
export type TestType = "Positive" | "Negative" | "Edge" | "Boundary";
export type Decision = "CREATE" | "UPDATE" | "SKIP";
export type Verdict = "PASS" | "FAIL" | "ESCALATE";

export interface TestStep {
  step: number;
  action: string;
  expected: string;
}

export interface TestCase {
  id: string;
  title: string;
  description: string;
  priority: Priority;
  type: TestType;
  steps: TestStep[];
  decision: Decision;
  existing_tc_id: string | null;
  decision_reason: string;
}

export interface Scenario {
  scenario_id: string;
  scenario_text: string;
  ac_refs: string[];
  suggested_test_type: TestType;
}

export interface CoverageMap {
  by_type: Record<TestType, number>;
  type_diversity_pct: number;
}

export interface ReviewReport {
  quality_score_pct: number;
  grade: "A" | "B" | "C" | "D";
  verdict: Verdict;
  completeness: number;
  coverage: number;
  correctness: number;
  correctness_gate: "PASS" | "FAIL";
  correction_tasks: unknown[];
  recommendations: string[];
  escalate_diagnostic: string | null;
}

export interface TestPlan {
  plan_summary: string;
  total_cases: number;
  to_create: number;
  to_update: number;
  to_skip: number;
  work_avoided_pct: number;
  scenarios?: unknown[];
}

export interface RunResult {
  verdict: Verdict;
  grade: string;
  quality_score_pct: number;
  completeness: number;
  correctness: number;
  correctness_gate: string;
  plan: Pick<TestPlan, "to_create" | "to_update" | "to_skip" | "work_avoided_pct">;
  test_cases: TestCase[];
  review_report: ReviewReport;
  errors: string[];
  is_best_effort: boolean;
}

// ── WebSocket events (server → client) ────────────────────────────────────
export type GateName = "plan_review" | "test_review";

export type ServerEvent =
  | { type: "trace"; node: string; message: string; status: "running" | "complete" }
  | { type: "genui"; component: string; data: unknown }
  | {
      type: "hitl";
      gate: GateName;
      prompt: string;
      options: string[];
      plan_summary?: string;
      plan?: TestPlan;
      test_cases?: TestCase[];
    }
  | { type: "done"; written: { created: number; updated: number; skipped: number } }
  | { type: "result"; data: RunResult }
  | { type: "error"; message: string };

// ── Client → server ───────────────────────────────────────────────────────
export interface HitlResponse {
  type: "hitl_response";
  choice: string;
  test_cases_edited?: TestCase[];
}

// ── Run request (POST /runs) — mirrors §1.4 ──────────────────────────────
export interface RunRequest {
  userStory: string;
  acceptanceCriteria?: string;
  projectId: string;
  jiraStoryId?: string;
  trigger_type?: "manual" | "api" | "webhook";
  options?: {
    priority?: Priority;
    includeEdgeCases?: boolean;
    testTypes?: TestType[];
  };
}
