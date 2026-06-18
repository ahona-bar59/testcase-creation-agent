import { useState } from "react";
import type { Priority, RunRequest } from "../types";

const SAMPLE_STORY =
  "As a registered user, I want to reset my password via an email link so that I can regain access if I forget it.";
const SAMPLE_ACS =
  "AC-1: A logged-out user can request a reset by entering a registered email.\n" +
  "AC-2: The reset link expires after 30 minutes.\n" +
  "AC-3: An unregistered email shows a generic message and sends no link.\n" +
  "AC-4: The new password must meet the complexity policy.";

export function NewRun({ onStart }: { onStart: (req: RunRequest) => void }) {
  const [userStory, setUserStory] = useState(SAMPLE_STORY);
  const [acceptanceCriteria, setAcceptanceCriteria] = useState(SAMPLE_ACS);
  const [projectId, setProjectId] = useState("DEMO-PROJ");
  const [priority, setPriority] = useState<Priority>("High");
  const [includeEdgeCases, setIncludeEdgeCases] = useState(true);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!userStory.trim() || !projectId.trim()) return;
    onStart({
      userStory,
      acceptanceCriteria,
      projectId,
      trigger_type: "manual",
      options: { priority, includeEdgeCases },
    });
  }

  return (
    <form className="card new-run" onSubmit={submit}>
      <h2>New test-case run</h2>

      <label>
        Project ID
        <input value={projectId} onChange={(e) => setProjectId(e.target.value)} required />
      </label>

      <label>
        User story
        <textarea
          rows={3}
          value={userStory}
          onChange={(e) => setUserStory(e.target.value)}
          required
        />
      </label>

      <label>
        Acceptance criteria <span className="muted">(one per line — optional)</span>
        <textarea
          rows={5}
          value={acceptanceCriteria}
          onChange={(e) => setAcceptanceCriteria(e.target.value)}
        />
      </label>

      <div className="row">
        <label>
          Priority
          <select value={priority} onChange={(e) => setPriority(e.target.value as Priority)}>
            <option>High</option>
            <option>Medium</option>
            <option>Low</option>
          </select>
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={includeEdgeCases}
            onChange={(e) => setIncludeEdgeCases(e.target.checked)}
          />
          Include edge cases
        </label>
      </div>

      <button className="btn primary lg" type="submit">
        Generate test cases →
      </button>
    </form>
  );
}
