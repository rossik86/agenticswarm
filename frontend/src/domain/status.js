const ROLE_AGENT_PREFIXES = {
  analyst: ["analyst_"],
  researcher: ["researcher"],
  reviewer: ["reviewer"],
  builder: ["builder"],
  supervisor: ["supervisor"],
  main: ["main"],
  learner: ["self_learner"],
};

export function getSelectedRun(runs = [], selectedRunId = "") {
  if (!selectedRunId) return null;
  return (runs || []).find((run) => run?.run_id === selectedRunId) || null;
}

export function selectAgentArtifacts(status = {}, agent = {}) {
  const name = String(agent?.name || "");
  if (!name) return [];
  return (status?.artifacts || []).filter((artifact) => artifact?.agent === name);
}

export function selectRoomArtifacts(status = {}, room = {}) {
  const role = String(room?.role || "");
  const prefixes = ROLE_AGENT_PREFIXES[role] || [role];
  return (status?.artifacts || []).filter((artifact) => {
    const agent = String(artifact?.agent || "");
    return prefixes.some((prefix) => agent === prefix || agent.startsWith(prefix));
  });
}
