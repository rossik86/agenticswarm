export function agentAction(agent = {}) {
  if (agent.status === "failed") return "blocked";
  if (agent.status !== "running") return "idle";
  const role = String(agent.role || agent.name || "");
  if (role.includes("research")) return "searching";
  if (role.includes("review")) return "reviewing";
  if (role.includes("builder")) return "typing";
  if (role.includes("analyst")) return "thinking";
  if (role.includes("learner")) return "learning";
  return "handoff";
}

export function ambientState(status = {}, events = []) {
  if (status?.status === "failed") return "alert";
  if ((events || []).some((event) => String(event.event || "").includes("approval"))) return "approval";
  if (status?.status === "completed") return "completed";
  if (status?.status === "running") return "running";
  return "idle";
}

export function conversationLine(agent = {}) {
  const name = String(agent.name || "");
  if (name.includes("positive")) return "Positive: szukam mocnych stron.";
  if (name.includes("negative")) return "Negative: grilluję ryzyka.";
  if (name.includes("neutral")) return "Neutral: podejmuję decyzję.";
  if (String(agent.role || "").includes("builder")) return "Builder: składam artefakt.";
  if (String(agent.role || "").includes("research")) return "Research: sprawdzam źródła.";
  if (String(agent.role || "").includes("review")) return "Review: weryfikuję jakość.";
  return "Przekazuję status.";
}

export function roomQueueCount(room = {}, events = []) {
  return (events || []).filter((event) => {
    const name = String(event.event || "").toLowerCase();
    return name.includes(room?.role || "") && (name.includes("started") || name.includes("requested"));
  }).length;
}
