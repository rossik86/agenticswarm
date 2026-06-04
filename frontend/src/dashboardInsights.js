export function buildQualityGates(room = {}, status = {}, checkpoints = []) {
  const agents = room?.agents || [];
  const artifacts = Array.isArray(status?.artifacts) ? status.artifacts : [];
  const roomArtifacts = artifacts.filter((artifact) => artifact.agent && agents.some((agent) => agent.name === artifact.agent));
  const roomErrors = agents.filter((agent) => agent.status === "failed" || agent.error);
  const roomCheckpoints = (checkpoints || []).filter((checkpoint) => String(checkpoint.node || "").includes(room?.role || ""));

  const gates = [
    gate("Agents completed", agents.length > 0 && agents.every((agent) => agent.status === "completed")),
    gate("Room artifact exists", room?.role === "main" || roomArtifacts.length > 0),
    gate("No room errors", roomErrors.length === 0),
  ];

  if (room?.role === "reviewer") {
    gates.push(gate("Review decision recorded", roomArtifacts.length > 0 || agents.some((agent) => String(agent.summary || "").trim())));
  }
  if (room?.role === "main") {
    gates.push(gate("Final answer ready", Boolean(status?.final_answer)));
  }
  if (roomCheckpoints.length) {
    gates.push(gate("Checkpoint available", true));
  }
  return gates;
}

export function buildAgentScorecards(status = {}) {
  const agents = Object.values(status?.agents || {});
  return agents
    .map((agent) => {
      const statusValue = String(agent.status || "idle");
      const tokens = Number(agent.token_usage?.total_tokens || 0);
      const hasError = statusValue === "failed" || Boolean(agent.error);
      const completed = statusValue === "completed";
      return {
        name: agent.display_name || agent.name,
        agent: agent.name,
        role: agent.role || "-",
        status: statusValue,
        tokens,
        score: hasError ? 35 : completed ? 100 : statusValue === "running" ? 65 : 50,
        summary: agent.summary || agent.error || "",
      };
    })
    .sort((left, right) => right.score - left.score || left.name.localeCompare(right.name));
}

export function summarizeRunDiff(diff = {}) {
  return [
    { label: "Score delta", value: signed(diff.score_delta), tone: tone(diff.score_delta) },
    { label: "Token delta", value: signed(diff.token_delta), tone: tone(-Number(diff.token_delta || 0)) },
    { label: "Artifact delta", value: signed(diff.artifact_delta), tone: tone(diff.artifact_delta) },
    { label: "Status changed", value: diff.status_changed ? "tak" : "nie", tone: diff.status_changed ? "warn" : "neutral" },
  ];
}

function gate(label, passed) {
  return { label, status: passed ? "passed" : "failed" };
}

function signed(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const number = Number(value);
  return number > 0 ? `+${number}` : String(number);
}

function tone(value) {
  const number = Number(value || 0);
  if (number > 0) return "good";
  if (number < 0) return "bad";
  return "neutral";
}
