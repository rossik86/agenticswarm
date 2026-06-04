import assert from "node:assert/strict";
import test from "node:test";
import { agentAction, ambientState, conversationLine } from "./townInteractions.js";

test("agentAction maps active roles to visible actions", () => {
  assert.equal(agentAction({ role: "researcher", status: "running" }), "searching");
  assert.equal(agentAction({ role: "reviewer", status: "running" }), "reviewing");
  assert.equal(agentAction({ role: "builder", status: "running" }), "typing");
});

test("ambientState prioritizes failed, approval and completed states", () => {
  assert.equal(ambientState({ status: "failed" }, []), "alert");
  assert.equal(ambientState({ status: "completed" }, []), "completed");
  assert.equal(ambientState({ status: "running" }, [{ event: "human.approval.requested" }]), "approval");
});

test("conversationLine describes council stance order", () => {
  assert.equal(conversationLine({ name: "analyst_positive", role: "analyst" }), "Positive: szukam mocnych stron.");
  assert.equal(conversationLine({ name: "analyst_negative", role: "analyst" }), "Negative: grilluję ryzyka.");
  assert.equal(conversationLine({ name: "analyst_neutral", role: "analyst" }), "Neutral: podejmuję decyzję.");
});
