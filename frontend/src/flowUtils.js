export function roleFromEvent(event) {
  const name = String(event?.event || "").toLowerCase();
  if (!name || name.includes("checkpoint")) return null;
  if (name.includes("main") || name.includes("final_response")) return "main";
  if (name.includes("supervisor")) return "supervisor";
  if (name.includes("research")) return "researcher";
  if (name.includes("analyst") || name.includes("analysis")) return "analyst";
  if (name.includes("builder") || name.includes("build_solution") || name.includes("build")) return "builder";
  if (name.includes("review")) return "reviewer";
  if (name.includes("learner") || name.includes("learning")) return "learner";
  return null;
}

export function flowStatusFromEvent(event) {
  const name = String(event?.event || "").toLowerCase();
  if (name.includes("failed") || name.includes("error")) return "failed";
  if (name.includes("started") || name.includes("running")) return "running";
  return "completed";
}

export function buildFlowSteps(events = []) {
  const roles = [];
  for (const event of events || []) {
    const role = roleFromEvent(event);
    if (!role) continue;
    const previous = roles[roles.length - 1];
    if (previous?.role === role) {
      previous.status = flowStatusFromEvent(event);
      previous.event = event.event;
      previous.at = event.at;
    } else {
      roles.push({
        role,
        status: flowStatusFromEvent(event),
        event: event.event,
        at: event.at,
      });
    }
  }
  if (!roles.length) return [];
  const steps = [];
  let previous = "start";
  roles.forEach((item, index) => {
    steps.push({
      index: index + 1,
      source: previous,
      target: item.role,
      status: item.status,
      event: item.event,
      at: item.at,
    });
    previous = item.role;
  });
  if (roles[roles.length - 1]?.status === "completed") {
    steps.push({
      index: steps.length + 1,
      source: previous,
      target: "end",
      status: "completed",
      event: "END",
      at: roles[roles.length - 1]?.at,
    });
  }
  return steps;
}

export function greenShade(index, total) {
  if (total <= 1) return "#1f8f4d";
  const lightness = 34 + Math.min(24, Math.round((index / Math.max(1, total - 1)) * 24));
  return `hsl(145 58% ${lightness}%)`;
}
