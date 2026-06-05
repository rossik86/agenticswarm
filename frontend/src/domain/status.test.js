import assert from "node:assert/strict";
import test from "node:test";
import { getSelectedRun, selectAgentArtifacts, selectRoomArtifacts } from "./status.js";

test("getSelectedRun tolerates missing selection and empty run list", () => {
  assert.equal(getSelectedRun([], ""), null);
  assert.equal(getSelectedRun([{ run_id: "run-1" }], ""), null);
});

test("getSelectedRun finds the active run by id", () => {
  assert.deepEqual(getSelectedRun([{ run_id: "run-1" }, { run_id: "run-2" }], "run-2"), { run_id: "run-2" });
});

test("artifact selectors filter by current run status only", () => {
  const status = {
    artifacts: [
      { agent: "builder", artifact_path: "builder.md" },
      { agent: "reviewer", artifact_path: "reviewer.md" },
      { agent: "analyst_neutral", artifact_path: "analyst.md" },
    ],
  };

  assert.deepEqual(selectAgentArtifacts(status, { name: "builder" }).map((artifact) => artifact.agent), ["builder"]);
  assert.deepEqual(selectRoomArtifacts(status, { role: "reviewer" }).map((artifact) => artifact.agent), ["reviewer"]);
});
