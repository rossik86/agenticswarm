import assert from "node:assert/strict";
import test from "node:test";
import { buildAgentScorecards, buildQualityGates, summarizeRunDiff } from "./dashboardInsights.js";

test("buildQualityGates marks builder complete only with artifacts", () => {
  const gates = buildQualityGates(
    { role: "builder", agents: [{ name: "builder", status: "completed" }] },
    { artifacts: [{ agent: "builder", artifact_path: "runs/1/builder.md" }] },
    [],
  );

  assert.deepEqual(
    gates.map((gate) => [gate.label, gate.status]),
    [
      ["Agents completed", "passed"],
      ["Room artifact exists", "passed"],
      ["No room errors", "passed"],
    ],
  );
});

test("buildQualityGates detects reviewer errors", () => {
  const gates = buildQualityGates(
    { role: "reviewer", agents: [{ name: "reviewer_negative", status: "failed", error: "security gap" }] },
    { artifacts: [] },
    [],
  );

  assert.equal(gates.find((gate) => gate.label === "No room errors").status, "failed");
});

test("buildAgentScorecards aggregates status and usage", () => {
  const scorecards = buildAgentScorecards({
    agents: {
      builder: { name: "builder", role: "builder", status: "completed", token_usage: { total_tokens: 120 } },
      reviewer: { name: "reviewer", role: "reviewer", status: "failed", token_usage: { total_tokens: 80 } },
    },
  });

  assert.equal(scorecards[0].name, "builder");
  assert.equal(scorecards[0].score, 100);
  assert.equal(scorecards[1].score, 35);
  assert.equal(scorecards[0].tokens, 120);
});

test("summarizeRunDiff creates readable delta labels", () => {
  const summary = summarizeRunDiff({ score_delta: 5, token_delta: -100, artifact_delta: 2, status_changed: true });

  assert.deepEqual(summary.map((item) => item.value), ["+5", "-100", "+2", "tak"]);
});
