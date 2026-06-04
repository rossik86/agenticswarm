import assert from "node:assert/strict";
import test from "node:test";
import { buildFlowSteps, greenShade } from "./flowUtils.js";

test("buildFlowSteps keeps repeated room transitions in order", () => {
  const steps = buildFlowSteps([
    { event: "agent.main_decision.completed", at: "1" },
    { event: "agent.supervisor.completed", at: "2" },
    { event: "agent.analyst_neutral.completed", at: "3" },
    { event: "agent.builder.completed", at: "4" },
    { event: "agent.reviewer.completed", at: "5" },
    { event: "agent.supervisor_gate.completed", at: "6" },
    { event: "agent.builder.completed", at: "7" },
  ]);

  assert.deepEqual(
    steps.map((step) => [step.source, step.target]),
    [
      ["start", "main"],
      ["main", "supervisor"],
      ["supervisor", "analyst"],
      ["analyst", "builder"],
      ["builder", "reviewer"],
      ["reviewer", "supervisor"],
      ["supervisor", "builder"],
      ["builder", "end"],
    ],
  );
});

test("greenShade produces different colors for sequential completed edges", () => {
  assert.notEqual(greenShade(0, 4), greenShade(3, 4));
});
