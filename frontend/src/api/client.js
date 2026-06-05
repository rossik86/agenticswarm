async function requestJson(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    throw new Error(`Request failed ${response.status}: ${path}`);
  }
  return response.json();
}

export function fetchStatus(runId = "") {
  const suffix = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
  return requestJson(`/status.json${suffix}`);
}

export function fetchRuns() {
  return requestJson("/runs.json");
}

export function fetchEvents(runId = "") {
  const suffix = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
  return requestJson(`/events.json${suffix}`);
}

export function fetchCheckpoints(runId = "") {
  const suffix = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
  return requestJson(`/checkpoints.json${suffix}`);
}

export function postJson(path, payload) {
  return requestJson(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
}
