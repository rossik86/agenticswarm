import assert from "node:assert/strict";
import test from "node:test";
import { compactRunId, filterRuns, runTimestamp, runTitle } from "./runUtils.js";

test("runTitle prefers readable user input over raw run id", () => {
  assert.equal(
    runTitle({ run_id: "20260604-142211-abcdef", user_input: "Przygotuj plan aplikacji lotto" }),
    "Przygotuj plan aplikacji lotto",
  );
});

test("compactRunId keeps only the useful tail of long ids", () => {
  assert.equal(compactRunId("20260604-142211-abcdef"), "42211-abcdef");
});

test("filterRuns searches text and status", () => {
  const runs = [
    { run_id: "a", status: "completed", user_input: "Plan aplikacji lotto", updated_at: "2026-06-04T10:00:00+02:00" },
    { run_id: "b", status: "failed", user_input: "CRM dashboard", updated_at: "2026-06-04T11:00:00+02:00" },
  ];

  assert.deepEqual(
    filterRuns(runs, { query: "lotto", status: "completed", datePreset: "all" }).map((run) => run.run_id),
    ["a"],
  );
});

test("filterRuns supports date presets", () => {
  const runs = [
    { run_id: "today", status: "completed", updated_at: "2026-06-04T10:00:00+02:00" },
    { run_id: "old", status: "completed", updated_at: "2026-05-01T10:00:00+02:00" },
  ];

  assert.deepEqual(
    filterRuns(runs, { datePreset: "7d", now: "2026-06-04T12:00:00+02:00" }).map((run) => run.run_id),
    ["today"],
  );
});

test("runTimestamp tolerates empty status before API loads", () => {
  assert.equal(runTimestamp(null), "");
});
