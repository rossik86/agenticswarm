export function compactRunId(runId = "") {
  const text = String(runId || "").trim();
  if (!text) return "no-run";
  return text.length <= 12 ? text : text.slice(-12);
}

export function runTitle(run = {}) {
  if (!run) return "Brak aktywnego runu";
  const input = normalizeText(run.user_input);
  if (input) return truncate(input, 54);
  const answer = normalizeText(run.final_answer);
  if (answer) return truncate(answer, 54);
  return `Run ${compactRunId(run.run_id)}`;
}

export function runPreview(run = {}) {
  if (!run) return "Brak wyniku";
  const answer = normalizeText(run.final_answer);
  if (answer) return truncate(answer, 78);
  const artifacts = Number(run.artifact_count || 0);
  return artifacts ? `${artifacts} artefaktów MD` : "Brak wyniku";
}

export function runTimestamp(run = {}) {
  if (!run) return "";
  return run.started_at || run.updated_at || "";
}

export function formatRunDate(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString("pl-PL", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function filterRuns(runs = [], filters = {}) {
  const query = normalizeText(filters.query).toLowerCase();
  const status = String(filters.status || "all");
  const datePreset = String(filters.datePreset || "all");
  const dateFrom = parseDate(filters.dateFrom);
  const dateTo = parseDate(filters.dateTo, true);
  const now = filters.now ? new Date(filters.now) : new Date();

  const filtered = (runs || []).filter((run) => {
    if (status !== "all" && String(run.status || "") !== status) return false;
    if (query && !runSearchText(run).includes(query)) return false;
    const timestamp = parseDate(runTimestamp(run));
    if (!matchesPreset(timestamp, datePreset, now)) return false;
    if (dateFrom && (!timestamp || timestamp < dateFrom)) return false;
    if (dateTo && (!timestamp || timestamp > dateTo)) return false;
    return true;
  });

  return filtered.sort((left, right) => compareRuns(left, right, filters.sort || "newest"));
}

function compareRuns(left, right, sort) {
  if (sort === "failed") {
    const leftFailed = left.status === "failed" ? 1 : 0;
    const rightFailed = right.status === "failed" ? 1 : 0;
    if (leftFailed !== rightFailed) return rightFailed - leftFailed;
  }
  const leftTime = parseDate(runTimestamp(left))?.getTime() || 0;
  const rightTime = parseDate(runTimestamp(right))?.getTime() || 0;
  return sort === "oldest" ? leftTime - rightTime : rightTime - leftTime;
}

function matchesPreset(timestamp, preset, now) {
  if (preset === "all") return true;
  if (!timestamp) return false;
  if (preset === "today") {
    return timestamp.toDateString() === now.toDateString();
  }
  if (preset === "7d") {
    const weekAgo = new Date(now);
    weekAgo.setDate(now.getDate() - 7);
    return timestamp >= weekAgo && timestamp <= now;
  }
  return true;
}

function runSearchText(run) {
  return [
    run.run_id,
    run.status,
    run.user_input,
    run.final_answer,
    run.started_at,
    run.updated_at,
  ].map(normalizeText).join(" ").toLowerCase();
}

function normalizeText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function truncate(value, limit) {
  const text = normalizeText(value);
  return text.length > limit ? `${text.slice(0, limit - 3)}...` : text;
}

function parseDate(value, endOfDay = false) {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  if (endOfDay && /^\d{4}-\d{2}-\d{2}$/.test(String(value))) {
    parsed.setHours(23, 59, 59, 999);
  }
  return parsed;
}
