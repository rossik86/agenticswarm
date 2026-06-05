import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Handle, MarkerType, Position, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Activity,
  AlertTriangle,
  Boxes,
  BrainCircuit,
  Calendar,
  CheckCircle2,
  Clock3,
  Database,
  FileText,
  Filter,
  PanelLeft,
  Play,
  Plus,
  RotateCcw,
  Save,
  Search,
  Settings,
  TerminalSquare,
  Trash2,
  GitCompare,
  History,
  ClipboardList,
  XCircle,
  Rocket
} from "lucide-react";
import roomTile from "./assets/pixel-room.png";
import commandRoom from "./assets/pixel-command-room.png";
import robotSprite from "./assets/pixel-robot.png";
import roomMain from "./assets/generated/room-main.png";
import roomSupervisor from "./assets/generated/room-supervisor.png";
import roomAnalyst from "./assets/generated/room-analyst.png";
import roomResearcher from "./assets/generated/room-researcher.png";
import roomBuilder from "./assets/generated/room-builder.png";
import roomReviewer from "./assets/generated/room-reviewer.png";
import roomLearner from "./assets/generated/room-learner.png";
import agentMain from "./assets/generated/agent-main.png";
import agentSupervisor from "./assets/generated/agent-supervisor.png";
import agentAnalystPositive from "./assets/generated/agent-analyst-positive.png";
import agentAnalystNegative from "./assets/generated/agent-analyst-negative.png";
import agentAnalystNeutral from "./assets/generated/agent-analyst-neutral.png";
import agentResearcher from "./assets/generated/agent-researcher.png";
import agentResearcherNegative from "./assets/generated/agent-researcher-negative.png";
import agentBuilder from "./assets/generated/agent-builder.png";
import agentReviewerPositive from "./assets/generated/agent-reviewer-positive.png";
import agentReviewerNegative from "./assets/generated/agent-reviewer-negative.png";
import agentReviewerNeutral from "./assets/generated/agent-reviewer-neutral.png";
import agentSelfLearner from "./assets/generated/agent-self-learner.png";
import { buildAgentScorecards, buildQualityGates, summarizeRunDiff } from "./dashboardInsights.js";
import { buildFlowSteps, flowStatusFromEvent, greenShade, roleFromEvent } from "./flowUtils.js";
import { compactRunId, filterRuns, formatRunDate, runPreview, runTimestamp, runTitle } from "./runUtils.js";
import { agentAction, ambientState, conversationLine, roomQueueCount } from "./townInteractions.js";
import "./styles.css";

const ROOMS = [
  { role: "analyst", label: "Analyst Council", x: 31, y: 25, kind: "council" },
  { role: "supervisor", label: "Supervisor Gate", x: 69, y: 25, kind: "single" },
  { role: "researcher", label: "Research Council", x: 26, y: 50, kind: "council" },
  { role: "learner", label: "Learning Lab", x: 74, y: 50, kind: "single" },
  { role: "builder", label: "Builder Bay", x: 31, y: 75, kind: "single" },
  { role: "reviewer", label: "Review Council", x: 69, y: 75, kind: "council" },
  { role: "main", label: "Main CO", x: 50, y: 50, kind: "command" }
];

const ROOM_AGENT_SLOTS = [
  { left: "27%", top: "57%" },
  { left: "50%", top: "63%" },
  { left: "68%", top: "53%" }
];

const ROOM_ASSETS = {
  main: roomMain,
  supervisor: roomSupervisor,
  analyst: roomAnalyst,
  researcher: roomResearcher,
  builder: roomBuilder,
  reviewer: roomReviewer,
  learner: roomLearner
};

const AGENT_ASSETS = {
  main: agentMain,
  supervisor: agentSupervisor,
  analyst_positive: agentAnalystPositive,
  analyst_negative: agentAnalystNegative,
  analyst_neutral: agentAnalystNeutral,
  researcher: agentResearcher,
  researcher_negative: agentResearcherNegative,
  builder: agentBuilder,
  reviewer_positive: agentReviewerPositive,
  reviewer_negative: agentReviewerNegative,
  reviewer: agentReviewerNeutral,
  self_learner: agentSelfLearner
};

const FLOW_NODE_TYPES = { flowRoom: FlowRoomNode };
const MODEL_OPTIONS = {
  agents_sdk: ["gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.3-codex", "gpt-5.3-codex-spark", "gpt-5.2"],
  codex_cli: ["gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.3-codex", "gpt-5.3-codex-spark", "gpt-5.2"],
  openhands: ["gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.3-codex", "gpt-5.3-codex-spark", "gpt-5.2", "local"],
  copilot: ["gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.3-codex", "gpt-5.3-codex-spark", "gpt-5.2", "copilot-default"]
};

function App() {
  const [status, setStatus] = useState(null);
  const [runs, setRuns] = useState([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [events, setEvents] = useState([]);
  const [checkpoints, setCheckpoints] = useState([]);
  const [selected, setSelected] = useState({ type: "room", id: "main" });
  const [autoSelectedFailure, setAutoSelectedFailure] = useState(false);
  const [pendingCheckpoint, setPendingCheckpoint] = useState(null);
  const [modal, setModal] = useState(null);
  const [agentSettings, setAgentSettings] = useState(null);
  const [settingsDrawerOpen, setSettingsDrawerOpen] = useState(false);
  const [resourcesDrawerOpen, setResourcesDrawerOpen] = useState(false);
  const [resources, setResources] = useState(null);
  const [onboarding, setOnboarding] = useState(null);
  const [welcomeOpen, setWelcomeOpen] = useState(false);
  const [learningPending, setLearningPending] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [runsDrawerOpen, setRunsDrawerOpen] = useState(false);
  const [notice, setNotice] = useState("");

  async function refresh() {
    const runQuery = selectedRunId ? `?run_id=${encodeURIComponent(selectedRunId)}` : "";
    const [statusResult, runsResult] = await Promise.all([
      fetch(`/status.json${runQuery}`, { cache: "no-store" }).then((response) => response.json()),
      fetch("/runs.json", { cache: "no-store" }).then((response) => response.json())
    ]);
    const effectiveRunQuery = statusResult.run_id ? `?run_id=${encodeURIComponent(statusResult.run_id)}` : runQuery;
    const [eventsResult, checkpointsResult] = await Promise.all([
      fetch(`/events.json${effectiveRunQuery}`, { cache: "no-store" }).then((response) => response.json()),
      fetch(`/checkpoints.json${effectiveRunQuery}`, { cache: "no-store" }).then((response) => response.json())
    ]);
    setStatus(statusResult);
    setRuns(runsResult.runs || []);
    setEvents((eventsResult.events || []).filter((event) => !statusResult.run_id || event.run_id === statusResult.run_id));
    setCheckpoints(checkpointsResult.checkpoints || []);
  }

  useEffect(() => {
    refresh().catch(() => setNotice("Nie mogę pobrać aktualnego statusu."));
    fetch("/onboarding.json", { cache: "no-store" })
      .then((response) => response.json())
      .then((data) => {
        setOnboarding(data);
        if (!data.configured) setWelcomeOpen(true);
      })
      .catch(() => {});
    const timer = window.setInterval(() => {
      refresh().catch(() => setNotice("Odświeżenie statusu nie powiodło się."));
    }, 5000);
    return () => window.clearInterval(timer);
  }, [selectedRunId]);

  const agents = useMemo(() => Object.values(status?.agents || {}), [status]);
  const rooms = useMemo(() => {
    return ROOMS.map((room) => ({
      ...room,
      agents: agents.filter((agent) => agent.role === room.role)
    }));
  }, [agents]);

  const selectedAgent = selected.type === "agent" ? agents.find((agent) => agent.name === selected.id) : null;
  const selectedRoom = selected.type === "room" ? rooms.find((room) => room.role === selected.id) : null;

  useEffect(() => {
    if (autoSelectedFailure) return;
    const failedAgent = agents.find((agent) => agent.status === "failed");
    if (failedAgent) {
      setSelected({ type: "agent", id: failedAgent.name });
      setAutoSelectedFailure(true);
    }
  }, [agents, autoSelectedFailure]);

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <h1>Multiagent Swarm Town</h1>
          <p>Pixel-art operations view, odświeżanie co 5 sekund</p>
        </div>
        <RunStatus
          status={status}
          runs={runs}
          selectedRunId={selectedRunId}
          onSelectRun={setSelectedRunId}
          onOpenRuns={() => setRunsDrawerOpen(true)}
        />
      </header>

      <section className="workspace">
        <button
          className="global-config-trigger"
          type="button"
          title="Zarządzanie agentami, skillami i MCP"
          onClick={async () => {
            setNotice("Pobieram globalną konfigurację.");
            const data = await fetch("/resources.json", { cache: "no-store" }).then((item) => item.json());
            setResources(data);
            setResourcesDrawerOpen(true);
            setNotice("");
          }}
        >
          <PanelLeft size={18} />
        </button>
        <OfficeMap
          rooms={rooms}
          status={status}
          onSelect={(nextSelection) => {
            setSelected(nextSelection);
            setInspectorOpen(true);
          }}
          selected={selected}
          events={events}
          agents={agents}
          onTownAction={async (payload) => {
            const response = await fetch("/town/action", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(payload)
            }).then((item) => item.json());
            setNotice(response.message || "Akcja town zapisana.");
            await refresh();
          }}
        />
        <button
          className="inspector-trigger"
          type="button"
          title="Pokaż dane pokoju/agenta"
          onClick={() => setInspectorOpen(true)}
        >
          <TerminalSquare size={18} />
        </button>
        <aside className={`inspector-drawer ${inspectorOpen ? "open" : ""}`} aria-label="Dane pokoju lub agenta">
          <button className="drawer-close" type="button" onClick={() => setInspectorOpen(false)}>
            Zamknij
          </button>
          <Inspector
            status={status}
            events={events}
            checkpoints={checkpoints}
            selectedAgent={selectedAgent}
            selectedRoom={selectedRoom}
            onOpenText={setModal}
            onCheckpointAction={async (action, checkpoint) => {
              const pendingKey = `${action}-${checkpoint.id}`;
              setPendingCheckpoint(pendingKey);
              setNotice(`${action === "resume" ? "Wznawiam" : "Restartuję"} checkpoint ${checkpoint.node}...`);
              try {
                const response = await fetch(`/checkpoint/${action}`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ checkpoint_id: checkpoint.id, run_id: checkpoint.run_id, node: checkpoint.node })
                }).then((item) => item.json());
                setNotice(response.message || "Akcja checkpointu przyjęta.");
                await refresh();
              } finally {
                window.setTimeout(() => setPendingCheckpoint(null), 1200);
              }
            }}
            pendingCheckpoint={pendingCheckpoint}
            onOpenAgentSettings={async (agent) => {
              setNotice(`Pobieram konfigurację agenta: ${displayAgentName(agent)}`);
              const settings = await fetch(`/agent-settings.json?agent=${encodeURIComponent(agent.name)}`, { cache: "no-store" }).then((item) =>
                item.json()
              );
              setAgentSettings(settings.agent);
              setSettingsDrawerOpen(true);
              setNotice("");
            }}
            learningPending={learningPending}
            onTownAction={async (payload) => {
              const response = await fetch("/town/action", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
              }).then((item) => item.json());
              setNotice(response.message || "Akcja town zapisana.");
              await refresh();
            }}
            onImproveFromLearning={async () => {
              if (!status?.run_id) return;
              setLearningPending(true);
              setNotice("Przygotowuję plan poprawy według learningu.");
              try {
                const response = await fetch("/learning/improve", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ run_id: status.run_id })
                }).then((item) => item.json());
                setNotice(response.message || "Akcja learning improvement przyjęta.");
                await refresh();
              } finally {
                setLearningPending(false);
              }
            }}
            onApplyLearningProposals={async (proposalIds) => {
              if (!status?.run_id || !proposalIds.length) return;
              setLearningPending(true);
              setNotice("Zastosowuję wybrane propozycje learnera.");
              try {
                const response = await fetch("/learning/proposals/apply", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ run_id: status.run_id, proposal_ids: proposalIds })
                }).then((item) => item.json());
                setNotice(response.message || "Propozycje learnera zastosowane.");
                await refresh();
              } finally {
                setLearningPending(false);
              }
            }}
          />
        </aside>
      </section>

      {notice ? (
        <button className="toast" type="button" onClick={() => setNotice("")}>
          {notice}
        </button>
      ) : null}
      {modal ? <TextModal modal={modal} onClose={() => setModal(null)} /> : null}
      {settingsDrawerOpen ? (
        <AgentSettingsDrawer
          settings={agentSettings}
          onSelectAgent={async (agentName) => {
            const settings = await fetch(`/agent-settings.json?agent=${encodeURIComponent(agentName)}`, { cache: "no-store" }).then((item) =>
              item.json()
            );
            setAgentSettings(settings.agent);
          }}
          onClose={() => setSettingsDrawerOpen(false)}
          onSave={async (nextSettings) => {
            setNotice(`Zapisuję model dla: ${nextSettings.name}`);
            const response = await fetch("/agent-settings.json", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(nextSettings)
            }).then((item) => item.json());
            setNotice(response.message || "Ustawienia zapisane.");
            if (response.agent) setAgentSettings(response.agent);
            await refresh();
          }}
        />
      ) : null}
      {resourcesDrawerOpen ? (
        <GlobalResourcesDrawer
          resources={resources}
          runs={runs}
          onOpenText={setModal}
          onClose={() => setResourcesDrawerOpen(false)}
          onReload={async () => {
            const data = await fetch("/resources.json", { cache: "no-store" }).then((item) => item.json());
            setResources(data);
          }}
          onboarding={onboarding || resources?.onboarding}
          onConfigureWelcome={async (payload) => {
            const response = await saveWelcomeConfiguration(payload);
            const data = await fetch("/resources.json", { cache: "no-store" }).then((item) => item.json());
            setResources(data);
            return response;
          }}
          onSave={async (payload) => {
            const response = await fetch("/resources.json", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(payload)
            }).then((item) => item.json());
            setNotice(response.message || "Zasób zapisany.");
            const data = await fetch("/resources.json", { cache: "no-store" }).then((item) => item.json());
            setResources(data);
            await refresh();
          }}
        />
      ) : null}
      {runsDrawerOpen ? (
        <RunPickerDrawer
          status={status}
          runs={runs}
          selectedRunId={selectedRunId}
          onSelectRun={(runId) => {
            setSelectedRunId(runId);
            setRunsDrawerOpen(false);
          }}
          onClose={() => setRunsDrawerOpen(false)}
        />
      ) : null}
      {welcomeOpen ? (
        <WelcomeConfigurationModal
          onboarding={onboarding}
          onClose={() => setWelcomeOpen(false)}
          onSave={async (payload) => {
            await saveWelcomeConfiguration(payload);
            setWelcomeOpen(false);
          }}
        />
      ) : null}
    </main>
  );

  async function saveWelcomeConfiguration(payload) {
    setNotice("Zapisuję konfigurację startową dla wszystkich agentów.");
    const response = await fetch("/onboarding.json", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then((item) => item.json());
    setNotice(response.message || "Konfiguracja startowa zapisana.");
    if (response.onboarding) setOnboarding(response.onboarding);
    await refresh();
    return response;
  }
}

function RunStatus({ status, runs, selectedRunId, onOpenRuns }) {
  const state = status?.status || "waiting";
  const Icon = state === "completed" ? CheckCircle2 : state === "failed" ? XCircle : Activity;
  const currentRun = status?.run_id ? { ...status, run_id: status.run_id } : null;
  return (
    <div className={`run-status ${state}`}>
      <div className="run-status-main">
        <Icon size={18} />
        <span>{state}</span>
        <strong>{currentRun ? runTitle(currentRun) : "Brak aktywnego runu"}</strong>
        <small>
          {selectedRunId ? "selected" : "latest"} · {compactRunId(status?.run_id)} · {formatRunDate(runTimestamp(status))}
        </small>
      </div>
      <button className="run-status-button" type="button" onClick={onOpenRuns} title="Pokaż listę runów">
        <History size={15} />
        Runs
        <em>{runs.length}</em>
      </button>
    </div>
  );
}

function RunPickerDrawer({ status, runs, selectedRunId, onSelectRun, onClose }) {
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [datePreset, setDatePreset] = useState("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [sort, setSort] = useState("newest");
  const [compareRunId, setCompareRunId] = useState("");
  const [runDiff, setRunDiff] = useState(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const visibleRuns = useMemo(
    () => filterRuns(runs, { query, status: statusFilter, datePreset, dateFrom, dateTo, sort }),
    [runs, query, statusFilter, datePreset, dateFrom, dateTo, sort]
  );
  const activeRunId = selectedRunId || status?.run_id || "";
  return (
    <div className="drawer-backdrop" role="presentation" onClick={onClose}>
      <section className="run-picker-drawer" role="dialog" aria-modal="true" aria-label="Lista runów" onClick={(event) => event.stopPropagation()}>
        <header>
          <div>
            <h2>Runs</h2>
            <p>{visibleRuns.length} / {runs.length} widocznych</p>
          </div>
          <button type="button" onClick={onClose}>Zamknij</button>
        </header>
        <div className="run-search-box">
          <Search size={15} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Szukaj po nazwie, wyniku, ID..."
            autoFocus
          />
        </div>
        <div className="run-filter-grid">
          <label>
            <span><Filter size={13} /> Status</span>
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="all">wszystkie</option>
              <option value="running">running</option>
              <option value="completed">completed</option>
              <option value="failed">failed</option>
              <option value="artifact_only">artifact only</option>
            </select>
          </label>
          <label>
            <span><Calendar size={13} /> Data</span>
            <select value={datePreset} onChange={(event) => setDatePreset(event.target.value)}>
              <option value="all">cały zakres</option>
              <option value="today">dzisiaj</option>
              <option value="7d">ostatnie 7 dni</option>
            </select>
          </label>
          <label>
            <span>Sort</span>
            <select value={sort} onChange={(event) => setSort(event.target.value)}>
              <option value="newest">najnowsze</option>
              <option value="oldest">najstarsze</option>
              <option value="failed">błędy najpierw</option>
            </select>
          </label>
          <label>
            <span>Od</span>
            <input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
          </label>
          <label>
            <span>Do</span>
            <input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
          </label>
        </div>
        <div className="run-picker-actions">
          <button type="button" className={!selectedRunId ? "active" : ""} onClick={() => onSelectRun("")}>
            Latest
          </button>
          <button
            type="button"
            onClick={() => {
              setQuery("");
              setStatusFilter("all");
              setDatePreset("all");
              setDateFrom("");
              setDateTo("");
              setSort("newest");
            }}
          >
            Wyczyść filtry
          </button>
        </div>
        <section className="run-diff-panel">
          <div>
            <strong>Run diff</strong>
            <span>Porównaj aktywny run z innym przebiegiem.</span>
          </div>
          <select value={compareRunId} onChange={(event) => setCompareRunId(event.target.value)}>
            <option value="">wybierz run do porównania</option>
            {runs.filter((run) => run.run_id !== activeRunId).map((run) => (
              <option key={run.run_id} value={run.run_id}>{runTitle(run)} · {compactRunId(run.run_id)}</option>
            ))}
          </select>
          <button
            type="button"
            disabled={!activeRunId || !compareRunId || diffLoading}
            onClick={async () => {
              setDiffLoading(true);
              try {
                const data = await fetch(`/run-diff.json?base=${encodeURIComponent(activeRunId)}&target=${encodeURIComponent(compareRunId)}`, { cache: "no-store" }).then((item) => item.json());
                setRunDiff(data);
              } finally {
                setDiffLoading(false);
              }
            }}
          >
            <GitCompare size={14} />
            {diffLoading ? "Porównuję..." : "Porównaj"}
          </button>
          {runDiff ? (
            <div className="run-diff-summary">
              {summarizeRunDiff(runDiff).map((item) => (
                <div className={item.tone} key={item.label}>
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                </div>
              ))}
            </div>
          ) : null}
        </section>
        <div className="run-card-list">
          {visibleRuns.length ? visibleRuns.map((run) => (
            <button
              type="button"
              className={`run-card ${run.run_id === activeRunId ? "active" : ""} ${run.status || "unknown"}`}
              key={run.run_id}
              onClick={() => onSelectRun(run.run_id)}
            >
              <div>
                <strong>{runTitle(run)}</strong>
                <span>{runPreview(run)}</span>
              </div>
              <aside>
                <mark>{run.status || "unknown"}</mark>
                <small>{formatRunDate(runTimestamp(run))}</small>
                <code>{compactRunId(run.run_id)}</code>
              </aside>
            </button>
          )) : <p className="muted">Brak runów pasujących do filtrów.</p>}
        </div>
      </section>
    </div>
  );
}

function OfficeMap({ rooms, status, onSelect, selected, events, agents, onTownAction }) {
  const officeRef = useRef(null);
  const [flowMode, setFlowMode] = useState(() => getFlowMode());
  const [officeSize, setOfficeSize] = useState({ width: 1000, height: 850 });
  const steps = useMemo(() => buildFlowSteps(events), [events]);
  const [activeStep, setActiveStep] = useState(0);
  const [replayPlaying, setReplayPlaying] = useState(false);
  useEffect(() => {
    const updateMode = () => setFlowMode(getFlowMode());
    window.addEventListener("resize", updateMode);
    return () => window.removeEventListener("resize", updateMode);
  }, []);
  useEffect(() => {
    setActiveStep((current) => {
      if (!steps.length) return 0;
      if (current <= 0 || current > steps.length) return steps.length;
      return current;
    });
  }, [steps.length]);
  useEffect(() => {
    if (!replayPlaying || !steps.length) return undefined;
    const timer = window.setInterval(() => {
      setActiveStep((current) => {
        if (current >= steps.length) {
          setReplayPlaying(false);
          return steps.length;
        }
        return current + 1;
      });
    }, 900);
    return () => window.clearInterval(timer);
  }, [replayPlaying, steps.length]);
  useEffect(() => {
    if (!officeRef.current) return undefined;
    const observer = new ResizeObserver(([entry]) => {
      setOfficeSize({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    observer.observe(officeRef.current);
    return () => observer.disconnect();
  }, []);
  const flow = useMemo(
    () => buildRunFlow(events, rooms, flowMode, officeSize, selected, onSelect, activeStep || steps.length, steps, onTownAction, status?.run_id),
    [events, rooms, flowMode, officeSize, selected, onSelect, activeStep, steps, onTownAction, status?.run_id]
  );
  const ambient = ambientState(status, events);
  return (
    <section className={`office-shell ambient-${ambient}`}>
      <AmbientBanner state={ambient} />
      <RunProgressPanel
        steps={steps}
        activeStep={activeStep || steps.length}
        replayPlaying={replayPlaying}
        onSelectStep={(step) => {
          setReplayPlaying(false);
          setActiveStep(step);
        }}
        onReplay={() => {
          if (!steps.length) return;
          setActiveStep(1);
          setReplayPlaying(true);
        }}
        onPause={() => setReplayPlaying(false)}
      />
      <section className={`office ambient-${ambient}`} aria-label="Agent town office" ref={officeRef}>
        <RunFlowOverlay flow={flow} onSelect={onSelect} selected={selected} />
        <div className="legacy-rooms" aria-hidden="true">{rooms.map((room) => (
          <Room key={room.role} room={room} onSelect={onSelect} selected={selected} />
        ))}</div>
      </section>
    </section>
  );
}

function AmbientBanner({ state }) {
  const labels = {
    alert: "ALERT: run zatrzymany na błędzie",
    approval: "APPROVAL: town czeka na decyzję",
    completed: "COMPLETED: run zakończony",
    running: "RUNNING: agenci pracują",
    idle: "IDLE: town gotowe"
  };
  return <div className={`ambient-banner ${state}`}>{labels[state] || labels.idle}</div>;
}

function RunProgressPanel({ steps, activeStep, replayPlaying, onSelectStep, onReplay, onPause }) {
  return (
    <section className="run-progress-panel" aria-label="Postęp runu checkpoint po checkpointcie">
      <div>
        <strong>Run progress</strong>
        <span>{steps.length ? `krok ${activeStep} / ${steps.length}` : "brak kroków"}</span>
      </div>
      <div className="replay-controls">
        <button type="button" disabled={!steps.length} onClick={replayPlaying ? onPause : onReplay}>
          {replayPlaying ? <Clock3 size={14} /> : <Play size={14} />}
          {replayPlaying ? "Pause" : "Replay"}
        </button>
      </div>
      <div className="progress-steps">
        {steps.length ? steps.map((step) => (
          <button
            type="button"
            key={`${step.index}-${step.source}-${step.target}`}
            className={`progress-step ${step.index === activeStep ? "active" : ""} ${step.status}`}
            onClick={() => onSelectStep(step.index)}
            title={`${step.source} -> ${step.target} · ${step.event}`}
          >
            <span>{step.index}</span>
            <strong>{step.source} {"->"} {step.target}</strong>
          </button>
        )) : <p className="muted">Run nie ma jeszcze zdarzeń flow.</p>}
      </div>
    </section>
  );
}

function RunFlowOverlay({ flow, onSelect, selected }) {
  return (
    <div className="flow-overlay" aria-label="Run flow overlay" data-edge-count={flow.edges.length}>
      <div className="flow-map-legend">
        <span><i className="done" /> wykonano</span>
        <span><i className="running" /> w trakcie</span>
        <span><i className="failed" /> błąd</span>
      </div>
      <ReactFlow
        key={flow.key}
        nodes={flow.nodes}
        edges={flow.edges}
        nodeTypes={FLOW_NODE_TYPES}
        fitView={false}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        zoomOnDoubleClick={false}
        preventScrolling={false}
        onlyRenderVisibleElements={false}
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_, node) => {
          if (node.id !== "start" && node.id !== "end") onSelect({ type: "room", id: node.id });
        }}
      />
    </div>
  );
}

function FlowRoomNode({ data }) {
  const image = roomAssetFor(data.role, data.kind);
  return (
    <div className={`flow-rf-node ${data.kind || ""} ${data.status || ""}`}>
      <Handle id="in" type="target" position={Position.Left} className="flow-handle" />
      {data.kind === "start" || data.kind === "end" ? (
        <div className="flow-terminal">
          <strong>{data.label}</strong>
          {data.subLabel ? <span>{data.subLabel}</span> : null}
        </div>
      ) : (
        <div
          className={`flow-room-card ${data.selected ? "selected" : ""} ${data.active ? "drop-ready" : ""}`}
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            const sourceAgent = event.dataTransfer.getData("text/agent");
            if (!sourceAgent || !data.onTownAction) return;
            data.onTownAction({
              action: "manual_handoff",
              run_id: data.runId,
              source: sourceAgent,
              target: data.role,
              reason: `Manual drag handoff to ${data.label}`
            });
          }}
        >
          <span className="room-light" />
          <img src={image} alt="" className="room-art" />
          <span className="room-name">{data.label}</span>
          <span className="room-count">{data.agentCount}</span>
          {data.queueCount ? <span className="room-queue">{data.queueCount}</span> : null}
          {(data.agents || []).map((agent, index) => (
            <AgentSprite key={agent.name} agent={agent} slot={ROOM_AGENT_SLOTS[index % ROOM_AGENT_SLOTS.length]} onSelect={data.onSelect} />
          ))}
          {data.failedAgent ? <ErrorBubble agent={data.failedAgent} /> : data.active ? <SpeechBubble agents={data.agents} council={data.agents?.length > 1} /> : null}
        </div>
      )}
      <Handle id="out" type="source" position={Position.Right} className="flow-handle" />
    </div>
  );
}

function Room({ room, onSelect, selected }) {
  const active = room.agents.some((agent) => agent.status === "running");
  const failed = room.agents.some((agent) => agent.status === "failed");
  const failedAgent = room.agents.find((agent) => agent.status === "failed");
  const image = roomAssetFor(room.role, room.kind);

  return (
    <button
      className={`room ${room.role} ${active ? "active" : ""} ${failed ? "failed" : ""} ${
        selected.type === "room" && selected.id === room.role ? "selected" : ""
      }`}
      type="button"
      style={{ left: `${room.x}%`, top: `${room.y}%` }}
      onClick={() => onSelect({ type: "room", id: room.role })}
    >
      <span className="room-light" />
      <img src={image} alt="" className="room-art" />
      <span className="room-name">{room.label}</span>
      <span className="room-count">{room.agents.length}</span>
      {room.agents.map((agent, index) => (
        <AgentSprite
          key={agent.name}
          agent={agent}
          slot={ROOM_AGENT_SLOTS[index % ROOM_AGENT_SLOTS.length]}
          onSelect={onSelect}
        />
      ))}
      {failedAgent ? <ErrorBubble agent={failedAgent} /> : active ? <SpeechBubble agents={room.agents} /> : null}
    </button>
  );
}

function AgentSprite({ agent, slot, onSelect }) {
  const action = agentAction(agent);
  const image = agentAssetFor(agent);
  return (
    <span
      className={`agent-sprite ${agent.status || "unknown"} action-${action}`}
      style={slot}
      role="button"
      tabIndex={0}
      draggable
      title={displayAgentName(agent)}
      onDragStart={(event) => {
        event.dataTransfer.setData("text/agent", agent.name);
        event.dataTransfer.effectAllowed = "move";
      }}
      onClick={(event) => {
        event.stopPropagation();
        onSelect({ type: "agent", id: agent.name });
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.stopPropagation();
          onSelect({ type: "agent", id: agent.name });
        }
      }}
    >
      <img src={image} alt="" />
      {agent.status === "failed" ? <span className="agent-error-mark">!</span> : null}
      {action !== "idle" ? <span className="agent-action">{action}</span> : null}
      <small>{shortName(displayAgentName(agent))}</small>
    </span>
  );
}

function ErrorBubble({ agent }) {
  const text = agent?.error || agent?.summary || "Agent zatrzymał się na błędzie.";
  return (
    <span className="speech error-speech">
      <AlertTriangle size={13} />
      <strong>{displayAgentName(agent)}</strong>
      <span>{text.slice(0, 82)}</span>
    </span>
  );
}

function SpeechBubble({ agents, council = false }) {
  const active = agents.find((agent) => agent.status === "running") || agents[0];
  const lines = council ? agents.slice(0, 3).map(conversationLine) : [active?.summary || active?.error || conversationLine(active)];
  return (
    <span className={`speech ${council ? "council-speech" : ""}`}>
      {lines.map((line, index) => <em key={`${line}-${index}`}>{line.slice(0, 74)}</em>)}
    </span>
  );
}

function Inspector({
  status,
  events,
  checkpoints,
  selectedAgent,
  selectedRoom,
  onCheckpointAction,
  pendingCheckpoint,
  onOpenText,
  onOpenAgentSettings,
  learningPending,
  onTownAction,
  onImproveFromLearning,
  onApplyLearningProposals
}) {
  if (selectedAgent) {
    const agentEvents = events.filter((event) => String(event.event || "").includes(selectedAgent.name));
    const agentCheckpoints = checkpoints.filter((checkpoint) => belongsToAgent(checkpoint, selectedAgent));
    return (
      <aside className="inspector">
        <PanelTitle
          icon={<TerminalSquare size={17} />}
          title={displayAgentName(selectedAgent)}
          subtitle={`${selectedAgent.name} · ${selectedAgent.role}`}
        />
        <KeyValue label="Status" value={selectedAgent.status} />
        <KeyValue label="Stance" value={selectedAgent.stance || "neutral"} />
        <AgentOptions agent={selectedAgent} onOpenAgentSettings={onOpenAgentSettings} />
        {selectedAgent.status === "failed" ? <ErrorCallout error={selectedAgent.error || selectedAgent.summary} /> : null}
        <CompactField label="Summary" value={selectedAgent.summary || selectedAgent.error || "-"} onOpen={onOpenText} />
        <ArtifactList artifacts={agentArtifacts(status, selectedAgent)} empty="Brak artefaktów tego agenta w tym runie." />
        <CheckpointList checkpoints={agentCheckpoints} onAction={onCheckpointAction} pendingCheckpoint={pendingCheckpoint} />
        <Timeline events={agentEvents} />
      </aside>
    );
  }

  const room = selectedRoom;
  const roomEvents = events.filter((event) => room?.agents?.some((agent) => String(event.event || "").includes(agent.name)));
  const roomCheckpoints = checkpoints.filter((checkpoint) => belongsToRoom(checkpoint, room?.role));
  const roomIo = room?.role ? status?.room_io?.[room.role] : null;
  const isMainRoom = room?.role === "main";
  return (
    <aside className="inspector">
      <PanelTitle icon={<Boxes size={17} />} title={room?.label || "Office"} subtitle={status?.run_id || "no-run"} />
      {isMainRoom ? (
        <RunIOPanel status={status} onOpen={onOpenText} />
      ) : (
        <>
          <CompactField label="Wejście pokoju" value={roomIo?.input || "-"} onOpen={onOpenText} />
          <CompactField label="Wyjście pokoju" value={roomIo?.output || roomOutput(room) || "-"} onOpen={onOpenText} />
        </>
      )}
      {isMainRoom ? <TopologyPanel topology={status?.execution_topology} onOpen={onOpenText} /> : null}
      <RoomConsole room={room} status={status} onTownAction={onTownAction} />
      {(isMainRoom || room?.role === "researcher" || room?.role === "builder" || room?.role === "reviewer") ? (
        <ClaimsPanel claims={status?.claims || []} onOpen={onOpenText} />
      ) : null}
      {(isMainRoom || room?.role === "learner") ? (
        <LearningProposalsPanel
          proposals={status?.learning_proposals || []}
          busy={learningPending}
          onApply={onApplyLearningProposals}
        />
      ) : null}
      <ResultPanel
        status={status}
        room={room}
        onOpen={onOpenText}
        learningPending={learningPending}
        onImproveFromLearning={onImproveFromLearning}
      />
      <QualityGatesPanel room={room} status={status} checkpoints={roomCheckpoints} />
      <TokenUsagePanel usage={status?.token_usage} selectedRole={room?.role} agents={room?.agents || []} showAllRoles={isMainRoom} />
      {isMainRoom ? <AgentScorecardsPanel status={status} /> : null}
      <CouncilList room={room} />
      <RoomHistory roomIo={roomIo} onOpen={onOpenText} />
      <CheckpointList checkpoints={roomCheckpoints} onAction={onCheckpointAction} pendingCheckpoint={pendingCheckpoint} />
      <Timeline events={roomEvents.length ? roomEvents : events.slice(-8)} />
    </aside>
  );
}

function AgentOptions({ agent, onOpenAgentSettings }) {
  return (
    <section className="agent-options">
      <button type="button" onClick={() => onOpenAgentSettings(agent)}>
        <Settings size={14} />
        Ustawienia agenta
      </button>
      <span>{displayAgentName(agent)}</span>
    </section>
  );
}

function RoomConsole({ room, status, onTownAction }) {
  const [note, setNote] = useState("");
  const [target, setTarget] = useState("builder");
  const [busy, setBusy] = useState(false);
  if (!room || !onTownAction) return null;
  async function submit(payload) {
    setBusy(true);
    try {
      await onTownAction(payload);
      setNote("");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel-section room-console">
      <h2>Room console</h2>
      <textarea
        rows={3}
        value={note}
        onChange={(event) => setNote(event.target.value)}
        placeholder={`Notatka dla pokoju ${room.label}`}
      />
      <div className="room-console-actions">
        <button
          type="button"
          disabled={busy || !note.trim()}
          onClick={() => submit({ action: "room_note", run_id: status?.run_id, room: room.role, note })}
        >
          Wyślij note
        </button>
        <select value={target} onChange={(event) => setTarget(event.target.value)}>
          {ROOMS.filter((item) => item.role !== room.role && item.role !== "main").map((item) => (
            <option key={item.role} value={item.role}>{item.label}</option>
          ))}
        </select>
        <button
          type="button"
          disabled={busy}
          onClick={() => submit({ action: "manual_handoff", run_id: status?.run_id, source: room.role, target, reason: note || "Manual room console handoff" })}
        >
          Handoff
        </button>
      </div>
    </section>
  );
}

function RunIOPanel({ status, onOpen }) {
  return (
    <section className="panel-section io-panel">
      <h2>Wejście / wyjście</h2>
      <CompactField label="Input" value={status?.user_input || status?.message || "-"} onOpen={onOpen} limit={150} />
      <CompactField label="Output" value={status?.final_answer || "-"} onOpen={onOpen} limit={150} />
      <CompactField label="Folder" value={status?.path || "-"} onOpen={onOpen} limit={90} />
    </section>
  );
}

function TopologyPanel({ topology, onOpen }) {
  const stages = topology?.stages || [];
  const edges = topology?.edges || [];
  return (
    <section className="panel-section topology-panel">
      <h2>Dynamic topology</h2>
      {stages.length ? (
        <>
          <div className="topology-stages">
            {stages.map((stage, index) => (
              <span key={`${stage}-${index}`}>{stage}</span>
            ))}
          </div>
          <button type="button" onClick={() => onOpen?.({ title: "Execution topology", text: JSON.stringify(topology, null, 2) })}>
            Pokaż DAG
          </button>
          <small>{edges.length} planned edges · {topology.mode || "static"}</small>
        </>
      ) : (
        <p className="muted">Brak dynamicznej topologii dla tego runu.</p>
      )}
    </section>
  );
}

function ClaimsPanel({ claims, onOpen }) {
  return (
    <section className="panel-section claims-panel">
      <h2>Grounding claims</h2>
      {claims.length ? (
        <div className="claims-list">
          {claims.slice(0, 5).map((claim) => (
            <button
              type="button"
              key={claim.id}
              onClick={() => onOpen?.({ title: `${claim.id} · ${claim.agent}`, text: JSON.stringify(claim, null, 2) })}
            >
              <strong>{claim.id}</strong>
              <span>{String(claim.claim || "").slice(0, 120)}</span>
              <small>{claim.confidence || "unknown"} · {claim.source || "no source"}</small>
            </button>
          ))}
        </div>
      ) : (
        <p className="muted">Brak claimów. Builder powinien oznaczać fakty domenowe jako wymagające weryfikacji.</p>
      )}
    </section>
  );
}

function LearningProposalsPanel({ proposals, busy, onApply }) {
  const [selected, setSelected] = useState([]);
  useEffect(() => {
    setSelected([]);
  }, [proposals]);
  function toggle(id) {
    setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  }
  return (
    <section className="panel-section learning-proposals-panel">
      <h2>Learning proposals</h2>
      {proposals.length ? (
        <>
          <div className="proposal-list">
            {proposals.slice(0, 8).map((proposal) => (
              <label key={proposal.id}>
                <input type="checkbox" checked={selected.includes(proposal.id)} onChange={() => toggle(proposal.id)} />
                <span>
                  <strong>{proposal.id} · {proposal.target}</strong>
                  <small>{proposal.action}</small>
                  {proposal.recommendation}
                </span>
              </label>
            ))}
          </div>
          <button type="button" disabled={busy || !selected.length} onClick={() => onApply?.(selected)}>
            <Save size={14} /> Zastosuj zaznaczone
          </button>
        </>
      ) : (
        <p className="muted">Brak strukturalnych propozycji learnera w tym runie.</p>
      )}
    </section>
  );
}

function ErrorCallout({ error }) {
  return (
    <div className="error-callout">
      <AlertTriangle size={15} />
      <strong>Agent utknął na błędzie</strong>
      <p>{String(error || "Brak szczegółów błędu.")}</p>
    </div>
  );
}

function CouncilList({ room }) {
  return (
    <section className="panel-section">
      <h2>Rada</h2>
      <div className="agent-list">
        {(room?.agents || []).map((agent) => (
            <div className="agent-row" key={agent.name}>
              <span className={`dot ${agent.status || "unknown"}`} />
            <span>{displayAgentName(agent)}</span>
            <small>{agent.stance || "neutral"}</small>
          </div>
        ))}
      </div>
    </section>
  );
}

function RoomHistory({ roomIo, onOpen }) {
  const history = roomIo?.history || [];
  return (
    <section className="panel-section">
      <h2>Historia pokoju</h2>
      {history.length ? (
        <div className="room-history">
          {history.slice(-6).reverse().map((entry, index) => (
            <button
              type="button"
              key={`${entry.updated_at}-${index}`}
              onClick={() =>
                onOpen({
                  title: `${entry.room} · ${entry.updated_at}`,
                  text: `INPUT\n${entry.input || "-"}\n\nOUTPUT\n${entry.output || "-"}`
                })
              }
            >
              <strong>{entry.summary || entry.room}</strong>
              <span>{entry.updated_at}</span>
            </button>
          ))}
        </div>
      ) : (
        <p className="muted">Brak wejścia/wyjścia dla tego pokoju w aktualnym runie.</p>
      )}
    </section>
  );
}

function CheckpointList({ checkpoints, onAction, pendingCheckpoint }) {
  return (
    <section className="panel-section">
      <h2>Checkpointy</h2>
      <div className="checkpoint-list">
        {checkpoints.length ? (
          checkpoints.map((checkpoint) => (
            <div className="checkpoint" key={checkpoint.id}>
              <div>
                <strong>{checkpoint.node}</strong>
                <span>{checkpoint.created_at}</span>
              </div>
              <div className="checkpoint-actions">
                <button
                  type="button"
                  title="Resume"
                  disabled={pendingCheckpoint === `resume-${checkpoint.id}`}
                  onClick={() => onAction("resume", checkpoint)}
                >
                  <Play size={14} />
                </button>
                <button
                  type="button"
                  title="Restart review"
                  disabled={pendingCheckpoint === `restart-${checkpoint.id}`}
                  onClick={() => onAction("restart", checkpoint)}
                >
                  <RotateCcw size={14} />
                </button>
              </div>
            </div>
          ))
        ) : (
          <p className="muted">Brak checkpointów dla tej roli.</p>
        )}
      </div>
    </section>
  );
}

function Timeline({ events }) {
  return (
    <section className="panel-section">
      <h2>Historia</h2>
      <div className="timeline">
        {events.slice(-10).reverse().map((event, index) => {
          const failed = isFailureEvent(event);
          const Icon = failed ? AlertTriangle : Clock3;
          return (
          <div className={`timeline-item ${failed ? "failed-event" : ""}`} key={`${event.at}-${event.event}-${index}`}>
            <Icon size={13} />
            <div>
              <strong>{event.event}</strong>
              <span>{event.at}</span>
            </div>
          </div>
          );
        })}
        {!events.length ? <p className="muted">Brak zdarzeń.</p> : null}
      </div>
    </section>
  );
}

function PanelTitle({ icon, title, subtitle }) {
  return (
    <div className="panel-title">
      {icon}
      <div>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
    </div>
  );
}

function KeyValue({ label, value }) {
  return (
    <div className="kv-line">
      <span>{label}</span>
      <strong>{String(value || "-")}</strong>
    </div>
  );
}

function CompactField({ label, value, onOpen, limit = 220 }) {
  const text = String(value || "-");
  const compact = text.length > limit ? `${text.slice(0, limit).trim()}...` : text;
  return (
    <div className="kv-line compact-line">
      <span>{label}</span>
      <strong>
        {compact}
        {text.length > limit ? (
          <button type="button" className="more-button" onClick={() => onOpen({ title: label, text })}>
            ...
          </button>
        ) : null}
      </strong>
    </div>
  );
}

function ResultPanel({ status, room, onOpen, learningPending, onImproveFromLearning }) {
  const artifacts = room?.role === "main" ? collectArtifacts(status) : roomArtifacts(status, room);
  const finalAnswer = status?.final_answer;
  const learningArtifact = collectArtifacts(status).find((artifact) => artifact.agent === "self_learner");
  const canImprove = Boolean(onImproveFromLearning && status?.run_id && learningArtifact && ["completed", "needs_revision"].includes(status?.status));
  return (
    <section className="panel-section result-panel">
      <h2>Wynik pracy</h2>
      {canImprove && (room?.role === "main" || room?.role === "learner") ? (
        <button className="learning-improve-button" type="button" disabled={learningPending} onClick={onImproveFromLearning}>
          <BrainCircuit size={14} />
          {learningPending ? "Przygotowuję plan..." : "Przygotuj poprawę według learningu"}
        </button>
      ) : null}
      {room?.role === "main" && finalAnswer ? (
        <CompactField label="Final" value={finalAnswer} onOpen={onOpen} limit={180} />
      ) : (
        <p className="muted">{artifacts.length ? "Artefakty agentów w tym pokoju." : "Brak artefaktów dla tego pokoju w aktualnym runie."}</p>
      )}
      <ArtifactList artifacts={artifacts} empty="Brak artefaktów." />
    </section>
  );
}

function TokenUsagePanel({ usage, selectedRole, agents = [], showAllRoles = false }) {
  const total = usage?.total_tokens || 0;
  const roles = usage?.by_role || {};
  const byAgent = usage?.by_agent || {};
  const roleEntries = Object.entries(roles);
  const selectedRoleUsage = roles[selectedRole] || {};
  const agentEntries = agents.map((agent) => [agent.name, byAgent[agent.name] || agent.token_usage || {}]);
  return (
    <section className="panel-section token-panel">
      <h2>Token usage</h2>
      <div className="token-total">
        <strong>{formatNumber(showAllRoles ? total : selectedRoleUsage.total_tokens || 0)}</strong>
        <span>{showAllRoles ? usage?.calls || 0 : selectedRoleUsage.calls || 0} calls</span>
      </div>
      {showAllRoles ? (
        <div className="token-rooms">
          {roleEntries.length ? (
          roleEntries.map(([role, roleUsage]) => (
            <div className={`token-room ${role === selectedRole ? "selected" : ""}`} key={role}>
              <span>{role}</span>
              <strong>{formatNumber(roleUsage.total_tokens || 0)}</strong>
              <small>{roleUsage.calls || 0} calls · in {formatNumber(roleUsage.input_tokens || 0)} / out {formatNumber(roleUsage.output_tokens || 0)}</small>
            </div>
          ))
          ) : (
            <p className="muted">Brak danych token usage dla tego runu.</p>
          )}
        </div>
      ) : (
        <div className="token-rooms">
          {agentEntries.length ? (
            agentEntries.map(([agentName, agentUsage]) => (
              <div className="token-room" key={agentName}>
                <span>{displayAgentName({ name: agentName })}</span>
                <strong>{formatNumber(agentUsage.total_tokens || 0)}</strong>
                <small>{agentUsage.calls || 0} calls · in {formatNumber(agentUsage.input_tokens || 0)} / out {formatNumber(agentUsage.output_tokens || 0)}</small>
              </div>
            ))
          ) : (
            <p className="muted">Brak danych token usage dla tego pokoju.</p>
          )}
        </div>
      )}
    </section>
  );
}

function TextModal({ modal, onClose }) {
  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <section className="text-modal" role="dialog" aria-modal="true" aria-label={modal.title} onClick={(event) => event.stopPropagation()}>
        <header>
          <h2>{modal.title}</h2>
          <button type="button" onClick={onClose}>
            Zamknij
          </button>
        </header>
        <pre>{modal.text}</pre>
      </section>
    </div>
  );
}

function AgentSettingsDrawer({ settings, onClose, onSave }) {
  const [tab, setTab] = useState("runtime");
  const [provider, setProvider] = useState("default");
  const [model, setModel] = useState("");
  const [temperature, setTemperature] = useState("");
  const [descriptionText, setDescriptionText] = useState("");
  const [promptText, setPromptText] = useState("");
  const [skillsText, setSkillsText] = useState("");
  const [toolsText, setToolsText] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (!settings) return;
    setProvider(settings.provider || "default");
    setModel(settings.model || settings.effective_model || "");
    setTemperature(settings.temperature ?? "");
    setDescriptionText(settings.description || "");
    setPromptText(settings.prompt || "");
    setSkillsText((settings.skills || []).join("\n"));
    setToolsText((settings.tools || []).join("\n"));
  }, [settings]);
  if (!settings) {
    return (
      <div className="drawer-backdrop" role="presentation" onClick={onClose}>
        <aside className="settings-drawer" aria-label="Ustawienia agentów" onClick={(event) => event.stopPropagation()}>
          <header>
            <h2>Konfiguracja agenta</h2>
            <button type="button" onClick={onClose}>Zamknij</button>
          </header>
        </aside>
      </div>
    );
  }
  const selectedProvider = provider === "default" ? settings.effective_provider : provider;
  const modelOptions = MODEL_OPTIONS[selectedProvider] || settings.model_options || [];
  const rows = [
    ["Agent", settings.name],
    ["Nazwa", settings.display_name],
    ["Typ", settings.type],
    ["Provider active", settings.effective_provider || "-"],
    ["Model active", settings.effective_model || "-"],
    ["Prompt", settings.prompt_path || "-"]
  ];
  return (
    <div className="drawer-backdrop" role="presentation" onClick={onClose}>
      <section className="settings-drawer agent-config-drawer" role="dialog" aria-modal="true" aria-label="Konfiguracja agenta" onClick={(event) => event.stopPropagation()}>
        <header>
          <div>
            <h2>Konfiguracja agenta</h2>
            <p>{settings.display_name || settings.name}</p>
          </div>
          <button type="button" onClick={onClose}>
            Zamknij
          </button>
        </header>
        <div className="settings-agent-picker agent-scope-note">
          Edycja dotyczy tylko tego agenta. Globalny CRUD zasobów jest w belce po lewej.
        </div>
        <nav className="settings-tabs" aria-label="Sekcje ustawień">
          {[
            ["runtime", "Konfiguracja"],
            ["prompt", "Prompt"],
            ["instructions", "Instrukcje"],
            ["skills", "Skille MD"],
            ["mcp", "MCP / tools"]
          ].map(([id, label]) => (
            <button type="button" className={tab === id ? "active" : ""} onClick={() => setTab(id)} key={id}>{label}</button>
          ))}
        </nav>
        {tab === "runtime" ? <div className="settings-grid">
          <section>
            <h3>Konfiguracja</h3>
            {rows.map(([label, value]) => (
              <div className="kv-line" key={label}>
                <span>{label}</span>
                <strong>{String(value || "-")}</strong>
              </div>
            ))}
            <form
              className="runtime-form"
              onSubmit={async (event) => {
                event.preventDefault();
                setSaving(true);
                try {
                  await onSave({ agent: settings.name, provider, model, temperature });
                } finally {
                  setSaving(false);
                }
              }}
            >
              <label>
                <span>Provider</span>
                <select value={provider} onChange={(event) => setProvider(event.target.value)}>
                  <option value="default">default ({settings.effective_provider || "agents_sdk"})</option>
                  <option value="agents_sdk">agents_sdk</option>
                  <option value="codex_cli">codex_cli</option>
                  <option value="openhands">openhands</option>
                  <option value="copilot">copilot</option>
                </select>
              </label>
              <label>
                <span>Model</span>
                <input list={`model-options-${settings.name}`} value={model} onChange={(event) => setModel(event.target.value)} />
                <datalist id={`model-options-${settings.name}`}>
                  {modelOptions.map((option) => (
                    <option value={option} key={option} />
                  ))}
                </datalist>
              </label>
              <label>
                <span>Temperature</span>
                <input
                  type="number"
                  min="0"
                  max="2"
                  step="0.1"
                  value={temperature}
                  onChange={(event) => setTemperature(event.target.value)}
                />
              </label>
              <button type="submit" disabled={saving}>
                {saving ? "Zapisuję..." : "Zapisz runtime"}
              </button>
            </form>
          </section>
          <section>
            <h3>Skill labels</h3>
            <TagList values={settings.skills || []} empty="Brak skills." />
            <h3>Tools</h3>
            <TagList values={settings.tools || []} empty="Brak tools." />
            <h3>Relacje</h3>
            <TagList values={[...(settings.delegates_to || []), ...(settings.validates || [])]} empty="Brak relacji." />
          </section>
        </div> : null}
        {tab === "skills" ? <section className="prompt-section">
          <h3>Lista skilli</h3>
          <form
            className="settings-edit-form"
            onSubmit={async (event) => {
              event.preventDefault();
              setSaving(true);
              try {
                await onSave({ agent: settings.name, skills: skillsText });
              } finally {
                setSaving(false);
              }
            }}
          >
            <textarea value={skillsText} onChange={(event) => setSkillsText(event.target.value)} rows={7} />
            <button type="submit" disabled={saving}>{saving ? "Zapisuję..." : "Zapisz skille"}</button>
          </form>
          <h3>Skill markdowns</h3>
          <div className="skill-doc-list">
            {(settings.skill_markdowns || []).length ? (
              settings.skill_markdowns.map((skill) => (
                <article className="skill-doc" key={skill.path || skill.name}>
                  <header>
                    <strong>{skill.name}</strong>
                    <span>{skill.path}</span>
                  </header>
                  <pre>{skill.content}</pre>
                </article>
              ))
            ) : (
              <p className="muted">Brak plików markdown dla skills tego agenta.</p>
            )}
          </div>
        </section> : null}
        {tab === "prompt" ? <section className="prompt-section">
          <h3>Prompt</h3>
          <form
            className="settings-edit-form"
            onSubmit={async (event) => {
              event.preventDefault();
              setSaving(true);
              try {
                await onSave({ agent: settings.name, prompt: promptText });
              } finally {
                setSaving(false);
              }
            }}
          >
            <textarea value={promptText} onChange={(event) => setPromptText(event.target.value)} rows={16} />
            <button type="submit" disabled={saving}>{saving ? "Zapisuję..." : "Zapisz prompt"}</button>
          </form>
        </section> : null}
        {tab === "instructions" ? <section className="prompt-section">
          <h3>Instrukcje agenta</h3>
          <form
            className="settings-edit-form"
            onSubmit={async (event) => {
              event.preventDefault();
              setSaving(true);
              try {
                await onSave({ agent: settings.name, description: descriptionText });
              } finally {
                setSaving(false);
              }
            }}
          >
            <textarea value={descriptionText} onChange={(event) => setDescriptionText(event.target.value)} rows={7} />
            <button type="submit" disabled={saving}>{saving ? "Zapisuję..." : "Zapisz instrukcje"}</button>
          </form>
          <h3>Relacje</h3>
          <TagList values={[...(settings.delegates_to || []), ...(settings.validates || [])]} empty="Brak relacji." />
        </section> : null}
        {tab === "mcp" ? <section className="prompt-section">
          <h3>MCP / tools</h3>
          <form
            className="settings-edit-form"
            onSubmit={async (event) => {
              event.preventDefault();
              setSaving(true);
              try {
                await onSave({ agent: settings.name, tools: toolsText });
              } finally {
                setSaving(false);
              }
            }}
          >
            <textarea value={toolsText} onChange={(event) => setToolsText(event.target.value)} rows={7} />
            <button type="submit" disabled={saving}>{saving ? "Zapisuję..." : "Zapisz MCP/tools"}</button>
          </form>
          <h3>Dostępne skille</h3>
          <TagList values={settings.skills || []} empty="Brak skilli." />
        </section> : null}
      </section>
    </div>
  );
}

function GlobalResourcesDrawer({ resources, runs = [], onboarding, onOpenText, onClose, onSave, onReload, onConfigureWelcome }) {
  const [tab, setTab] = useState(resources?.onboarding?.configured ? "agents" : "start");
  const [selectedSkill, setSelectedSkill] = useState("");
  const [skillName, setSkillName] = useState("");
  const [skillContent, setSkillContent] = useState("");
  const [selectedMcp, setSelectedMcp] = useState("");
  const [mcpName, setMcpName] = useState("");
  const [mcpCommand, setMcpCommand] = useState("");
  const [mcpDescription, setMcpDescription] = useState("");
  const [mcpArgs, setMcpArgs] = useState("");
  const [mcpEnv, setMcpEnv] = useState("");
  const [templates, setTemplates] = useState([]);
  const [templateDraft, setTemplateDraft] = useState({ id: "", name: "", prompt: "", required_artifacts: "", quality_gates: "" });
  const [versions, setVersions] = useState([]);
  const [presets, setPresets] = useState([]);
  const [diffBase, setDiffBase] = useState("");
  const [diffTarget, setDiffTarget] = useState("");
  const [runDiff, setRunDiff] = useState(null);
  const [welcomeProvider, setWelcomeProvider] = useState("codex_cli");
  const [welcomeModel, setWelcomeModel] = useState("gpt-5.4-mini");
  const [healthResult, setHealthResult] = useState(null);
  const [saving, setSaving] = useState(false);
  const [rollingBackVersion, setRollingBackVersion] = useState("");
  const skills = resources?.skills || [];
  const mcps = resources?.mcp || [];
  const welcomeState = onboarding || resources?.onboarding || {};
  const welcomeProviderOptions = welcomeState.provider_options || ["agents_sdk", "codex_cli", "openhands", "copilot"];
  const welcomeModelOptions = MODEL_OPTIONS[welcomeProvider] || welcomeState.model_options || [];
  useEffect(() => {
    if (!welcomeState) return;
    setWelcomeProvider(welcomeState.provider || "codex_cli");
    setWelcomeModel(welcomeState.model || "gpt-5.4-mini");
  }, [welcomeState?.provider, welcomeState?.model]);
  useEffect(() => {
    const skill = skills.find((item) => item.name === selectedSkill) || skills[0];
    if (!skill) return;
    setSelectedSkill(skill.name);
    setSkillName(skill.name);
    setSkillContent(skill.content || "");
  }, [resources]);
  useEffect(() => {
    const mcp = mcps.find((item) => item.name === selectedMcp) || mcps[0];
    if (!mcp) return;
    setSelectedMcp(mcp.name);
    setMcpName(mcp.name);
    setMcpCommand(mcp.command || "");
    setMcpDescription(mcp.description || "");
    setMcpArgs((mcp.args || []).join("\n"));
    setMcpEnv(Object.entries(mcp.env || {}).map(([key, value]) => `${key}=${value}`).join("\n"));
  }, [resources]);
  useEffect(() => {
    if (tab === "templates") {
      fetch("/templates.json", { cache: "no-store" }).then((item) => item.json()).then((data) => setTemplates(data.templates || []));
    }
    if (tab === "versions") {
      fetch("/versions.json", { cache: "no-store" }).then((item) => item.json()).then((data) => setVersions(data.versions || []));
    }
    if (tab === "presets") {
      fetch("/presets.json", { cache: "no-store" }).then((item) => item.json()).then((data) => setPresets(data.presets || []));
    }
  }, [tab]);
  async function submit(payload) {
    setSaving(true);
    try {
      await onSave(payload);
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="drawer-backdrop" role="presentation" onClick={onClose}>
      <section className="settings-drawer global-resources-drawer" role="dialog" aria-modal="true" aria-label="Zarządzanie zasobami" onClick={(event) => event.stopPropagation()}>
        <header>
          <div>
            <h2>Zarządzanie</h2>
            <p>Globalne zasoby aplikacji</p>
          </div>
          <button type="button" onClick={onClose}>Zamknij</button>
        </header>
        <nav className="settings-tabs" aria-label="Globalne sekcje">
          {[
            ["start", "Start", Rocket],
            ["agents", "Agenci", Settings],
            ["skills", "Skille", FileText],
            ["mcp", "MCP", Database],
            ["presets", "Presets", BrainCircuit],
            ["templates", "Templates", ClipboardList],
            ["versions", "Versions", History],
            ["diff", "Diff", GitCompare]
          ].map(([id, label, Icon]) => (
            <button type="button" className={tab === id ? "active" : ""} onClick={() => setTab(id)} key={id}>
              <Icon size={14} />
              {label}
            </button>
          ))}
        </nav>
        {tab === "start" ? (
          <section className="resource-section welcome-config-panel">
            <h3>Welcome configuration</h3>
            <p className="muted">
              Ustaw provider i model dla całego swarmu. Zapis nadpisze te wartości w defaults oraz we wszystkich agentach.
            </p>
            <form className="settings-edit-form" onSubmit={async (event) => {
              event.preventDefault();
              setSaving(true);
              try {
                await onConfigureWelcome?.({ provider: welcomeProvider, model: welcomeModel });
                await onReload?.();
              } finally {
                setSaving(false);
              }
            }}>
              <label>
                <span>Provider</span>
                <select value={welcomeProvider} onChange={(event) => {
                  const nextProvider = event.target.value;
                  setWelcomeProvider(nextProvider);
                  setWelcomeModel((MODEL_OPTIONS[nextProvider] || [welcomeModel])[0] || welcomeModel);
                }}>
                  {welcomeProviderOptions.map((provider) => <option value={provider} key={provider}>{provider}</option>)}
                </select>
              </label>
              <label>
                <span>Model</span>
                <input list="welcome-model-options" value={welcomeModel} onChange={(event) => setWelcomeModel(event.target.value)} />
                <datalist id="welcome-model-options">
                  {welcomeModelOptions.map((option) => <option value={option} key={option} />)}
                </datalist>
              </label>
              <div className="welcome-config-summary">
                <KeyValue label="Configured" value={welcomeState.configured ? "tak" : "nie"} />
                <KeyValue label="Agents" value={welcomeState.agent_count ?? (resources?.agents || []).length} />
                <KeyValue label="Current provider" value={welcomeState.provider || "-"} />
                <KeyValue label="Current model" value={welcomeState.model || "-"} />
              </div>
              {healthResult ? (
                <div className={`health-result ${healthResult.ok ? "ok" : "failed"}`}>
                  <strong>{healthResult.ok ? "Provider działa" : "Provider nie działa"}</strong>
                  <span>{healthResult.message || healthResult.output || "-"}</span>
                </div>
              ) : null}
              <div className="form-actions">
                <button type="button" disabled={saving} onClick={async () => {
                  setSaving(true);
                  try {
                    const result = await fetch("/provider-health.json", {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ provider: welcomeProvider, model: welcomeModel })
                    }).then((item) => item.json());
                    setHealthResult(result);
                  } finally {
                    setSaving(false);
                  }
                }}>
                  <Activity size={14} /> Sprawdź provider
                </button>
                <button type="submit" disabled={saving}>
                  <Save size={14} /> Zapisz dla wszystkich agentów
                </button>
              </div>
            </form>
          </section>
        ) : null}
        {tab === "agents" ? (
          <section className="resource-section">
            <h3>Agenci</h3>
            <div className="resource-list">
              {(resources?.agents || []).map((agent) => (
                <article className="resource-card" key={agent.name}>
                  <strong>{agent.display_name || agent.name}</strong>
                  <span>{agent.name} · {agent.effective_provider} · {agent.effective_model}</span>
                  <small>{(agent.skills || []).length} skills · {(agent.tools || []).length} MCP/tools</small>
                </article>
              ))}
            </div>
          </section>
        ) : null}
        {tab === "skills" ? (
          <section className="resource-section">
            <div className="resource-toolbar">
              <select value={selectedSkill} onChange={(event) => {
                const skill = skills.find((item) => item.name === event.target.value);
                setSelectedSkill(event.target.value);
                setSkillName(skill?.name || "");
                setSkillContent(skill?.content || "");
              }}>
                {skills.map((skill) => <option value={skill.name} key={skill.name}>{skill.name}</option>)}
              </select>
              <button type="button" onClick={() => { setSelectedSkill(""); setSkillName(""); setSkillContent("# Nowy skill\n"); }}>
                <Plus size={14} /> Nowy
              </button>
            </div>
            <form className="settings-edit-form" onSubmit={(event) => {
              event.preventDefault();
              submit({ type: "skill", action: "save", name: skillName, content: skillContent });
            }}>
              <label><span>Nazwa</span><input value={skillName} onChange={(event) => setSkillName(event.target.value)} /></label>
              <textarea value={skillContent} onChange={(event) => setSkillContent(event.target.value)} rows={16} />
              <div className="form-actions">
                <button type="submit" disabled={saving}><Save size={14} /> Zapisz</button>
                <button type="button" disabled={saving || !skillName} onClick={() => submit({ type: "skill", action: "delete", name: skillName })}>
                  <Trash2 size={14} /> Usuń
                </button>
              </div>
            </form>
          </section>
        ) : null}
        {tab === "mcp" ? (
          <section className="resource-section">
            <div className="resource-toolbar">
              <select value={selectedMcp} onChange={(event) => {
                const mcp = mcps.find((item) => item.name === event.target.value);
                setSelectedMcp(event.target.value);
                setMcpName(mcp?.name || "");
                setMcpCommand(mcp?.command || "");
                setMcpDescription(mcp?.description || "");
                setMcpArgs((mcp?.args || []).join("\n"));
                setMcpEnv(Object.entries(mcp?.env || {}).map(([key, value]) => `${key}=${value}`).join("\n"));
              }}>
                {mcps.map((mcp) => <option value={mcp.name} key={mcp.name}>{mcp.name}</option>)}
              </select>
              <button type="button" onClick={() => { setSelectedMcp(""); setMcpName(""); setMcpCommand(""); setMcpDescription(""); setMcpArgs(""); setMcpEnv(""); }}>
                <Plus size={14} /> Nowy
              </button>
            </div>
            <form className="settings-edit-form" onSubmit={(event) => {
              event.preventDefault();
              submit({ type: "mcp", action: "save", name: mcpName, command: mcpCommand, description: mcpDescription, args: mcpArgs, env: mcpEnv });
            }}>
              <label><span>Nazwa</span><input value={mcpName} onChange={(event) => setMcpName(event.target.value)} /></label>
              <label><span>Command</span><input value={mcpCommand} onChange={(event) => setMcpCommand(event.target.value)} /></label>
              <label><span>Opis</span><textarea value={mcpDescription} onChange={(event) => setMcpDescription(event.target.value)} rows={3} /></label>
              <label><span>Args</span><textarea value={mcpArgs} onChange={(event) => setMcpArgs(event.target.value)} rows={5} /></label>
              <label><span>Env</span><textarea value={mcpEnv} onChange={(event) => setMcpEnv(event.target.value)} rows={5} /></label>
              <div className="form-actions">
                <button type="submit" disabled={saving}><Save size={14} /> Zapisz</button>
                <button type="button" disabled={saving || !mcpName} onClick={() => submit({ type: "mcp", action: "delete", name: mcpName })}>
                  <Trash2 size={14} /> Usuń
                </button>
              </div>
            </form>
          </section>
        ) : null}
        {tab === "presets" ? (
          <section className="resource-section">
            <h3>Agent presets</h3>
            <p className="muted">Preset ustawia modele, temperatury i dodatkowe skille dla wybranego typu pracy.</p>
            <div className="resource-list">
              {presets.map((preset) => (
                <article className="resource-card preset-card" key={preset.id}>
                  <strong>{preset.name}</strong>
                  <span>{preset.id}</span>
                  <small>{preset.description}</small>
                  <button type="button" disabled={saving} onClick={async () => {
                    setSaving(true);
                    try {
                      await fetch("/presets.json", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ preset: preset.id })
                      }).then((item) => item.json());
                      await onReload?.();
                    } finally {
                      setSaving(false);
                    }
                  }}>
                    <Save size={14} /> Zastosuj preset
                  </button>
                </article>
              ))}
              {!presets.length ? <p className="muted">Brak presetów.</p> : null}
            </div>
          </section>
        ) : null}
        {tab === "templates" ? (
          <section className="resource-section">
            <h3>Task templates</h3>
            <div className="resource-list">
              {templates.map((template) => (
                <button
                  className="resource-card as-button"
                  type="button"
                  key={template.id}
                  onClick={() =>
                    setTemplateDraft({
                      id: template.id || "",
                      name: template.name || "",
                      prompt: template.prompt || "",
                      required_artifacts: (template.required_artifacts || []).join("\n"),
                      quality_gates: (template.quality_gates || []).join("\n")
                    })
                  }
                >
                  <strong>{template.name}</strong>
                  <span>{template.id}</span>
                  <small>{(template.quality_gates || []).join(", ")}</small>
                </button>
              ))}
            </div>
            <form className="settings-edit-form template-form" onSubmit={async (event) => {
              event.preventDefault();
              setSaving(true);
              try {
                const response = await fetch("/templates.json", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify(templateDraft)
                }).then((item) => item.json());
                const data = await fetch("/templates.json", { cache: "no-store" }).then((item) => item.json());
                setTemplates(data.templates || []);
                if (response.template) setTemplateDraft({
                  id: response.template.id,
                  name: response.template.name,
                  prompt: response.template.prompt,
                  required_artifacts: (response.template.required_artifacts || []).join("\n"),
                  quality_gates: (response.template.quality_gates || []).join("\n")
                });
              } finally {
                setSaving(false);
              }
            }}>
              <label><span>ID</span><input value={templateDraft.id} onChange={(event) => setTemplateDraft({ ...templateDraft, id: event.target.value })} /></label>
              <label><span>Nazwa</span><input value={templateDraft.name} onChange={(event) => setTemplateDraft({ ...templateDraft, name: event.target.value })} /></label>
              <label><span>Prompt</span><textarea rows={5} value={templateDraft.prompt} onChange={(event) => setTemplateDraft({ ...templateDraft, prompt: event.target.value })} /></label>
              <label><span>Artefakty</span><textarea rows={4} value={templateDraft.required_artifacts} onChange={(event) => setTemplateDraft({ ...templateDraft, required_artifacts: event.target.value })} /></label>
              <label><span>Gate'y</span><textarea rows={4} value={templateDraft.quality_gates} onChange={(event) => setTemplateDraft({ ...templateDraft, quality_gates: event.target.value })} /></label>
              <button type="submit" disabled={saving}><Save size={14} /> Zapisz template</button>
            </form>
          </section>
        ) : null}
        {tab === "versions" ? (
          <section className="resource-section">
            <h3>Prompt / Skill versions</h3>
            <div className="resource-list">
              {versions.length ? versions.map((version) => (
                <article className="resource-card version-card" key={version.id}>
                  <button
                    className="as-button"
                    type="button"
                    onClick={() => onOpenText?.({ title: `${version.resource} · ${version.created_at}`, text: version.content || "" })}
                  >
                    <strong>{version.resource}</strong>
                    <span>{version.reason} · {version.created_at}</span>
                    <small>{version.id}</small>
                  </button>
                  <button
                    type="button"
                    disabled={rollingBackVersion === version.id}
                    onClick={async () => {
                      setRollingBackVersion(version.id);
                      try {
                        await fetch("/versions/rollback", {
                          method: "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({ version_id: version.id })
                        }).then((item) => item.json());
                        const data = await fetch("/versions.json", { cache: "no-store" }).then((item) => item.json());
                        setVersions(data.versions || []);
                        await onReload?.();
                      } finally {
                        setRollingBackVersion("");
                      }
                    }}
                  >
                    <RotateCcw size={14} />
                    Rollback
                  </button>
                </article>
              )) : <p className="muted">Brak wersji promptów/skilli.</p>}
            </div>
          </section>
        ) : null}
        {tab === "diff" ? (
          <section className="resource-section">
            <h3>Run diff</h3>
            <form className="settings-edit-form" onSubmit={async (event) => {
              event.preventDefault();
              const data = await fetch(`/run-diff.json?base=${encodeURIComponent(diffBase)}&target=${encodeURIComponent(diffTarget)}`, { cache: "no-store" }).then((item) => item.json());
              setRunDiff(data);
            }}>
              <label><span>Base run</span><select value={diffBase} onChange={(event) => setDiffBase(event.target.value)}>
                <option value="">wybierz</option>
                {runs.map((run) => <option key={run.run_id} value={run.run_id}>{run.run_id} · {run.status}</option>)}
              </select></label>
              <label><span>Target run</span><select value={diffTarget} onChange={(event) => setDiffTarget(event.target.value)}>
                <option value="">wybierz</option>
                {runs.map((run) => <option key={run.run_id} value={run.run_id}>{run.run_id} · {run.status}</option>)}
              </select></label>
              <button type="submit"><GitCompare size={14} /> Porównaj</button>
            </form>
            {runDiff ? (
              <div className="diff-grid">
                <KeyValue label="Score Δ" value={runDiff.score_delta ?? "-"} />
                <KeyValue label="Token Δ" value={runDiff.token_delta ?? "-"} />
                <KeyValue label="Artefakty Δ" value={runDiff.artifact_delta ?? "-"} />
                <KeyValue label="Status changed" value={runDiff.status_changed ? "tak" : "nie"} />
              </div>
            ) : null}
          </section>
        ) : null}
      </section>
    </div>
  );
}

function WelcomeConfigurationModal({ onboarding, onClose, onSave }) {
  const [provider, setProvider] = useState(onboarding?.provider || "codex_cli");
  const [model, setModel] = useState(onboarding?.model || "gpt-5.4-mini");
  const [saving, setSaving] = useState(false);
  const [healthResult, setHealthResult] = useState(null);
  const providerOptions = onboarding?.provider_options || ["agents_sdk", "codex_cli", "openhands", "copilot"];
  const modelOptions = MODEL_OPTIONS[provider] || onboarding?.model_options || [];
  return (
    <div className="drawer-backdrop welcome-backdrop" role="presentation" onClick={onClose}>
      <section className="welcome-modal" role="dialog" aria-modal="true" aria-label="Konfiguracja startowa" onClick={(event) => event.stopPropagation()}>
        <header>
          <div>
            <Rocket size={22} />
            <h2>Konfiguracja startowa</h2>
          </div>
          <p>Wybierz provider i model. Zapis zostanie zastosowany jednocześnie do wszystkich agentów.</p>
        </header>
        <form className="settings-edit-form" onSubmit={async (event) => {
          event.preventDefault();
          setSaving(true);
          try {
            await onSave({ provider, model });
          } finally {
            setSaving(false);
          }
        }}>
          <label>
            <span>Provider</span>
            <select value={provider} onChange={(event) => {
              const nextProvider = event.target.value;
              setProvider(nextProvider);
              setModel((MODEL_OPTIONS[nextProvider] || [model])[0] || model);
            }}>
              {providerOptions.map((option) => <option value={option} key={option}>{option}</option>)}
            </select>
          </label>
          <label>
            <span>Model</span>
            <input list="welcome-modal-model-options" value={model} onChange={(event) => setModel(event.target.value)} />
            <datalist id="welcome-modal-model-options">
              {modelOptions.map((option) => <option value={option} key={option} />)}
            </datalist>
          </label>
          {healthResult ? (
            <div className={`health-result ${healthResult.ok ? "ok" : "failed"}`}>
              <strong>{healthResult.ok ? "Provider działa" : "Provider nie działa"}</strong>
              <span>{healthResult.message || healthResult.output || "-"}</span>
            </div>
          ) : null}
          <div className="welcome-actions">
            <button type="button" disabled={saving} onClick={async () => {
              setSaving(true);
              try {
                const result = await fetch("/provider-health.json", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ provider, model })
                }).then((item) => item.json());
                setHealthResult(result);
              } finally {
                setSaving(false);
              }
            }}>
              <Activity size={14} /> Sprawdź provider
            </button>
            <button type="submit" disabled={saving}>
              <Save size={14} /> Zapisz i przejdź do dashboardu
            </button>
            <button type="button" onClick={onClose} disabled={saving}>
              Pomiń
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function TagList({ values, empty }) {
  return values.length ? (
    <div className="tag-list">
      {values.map((value) => (
        <span key={value}>{value}</span>
      ))}
    </div>
  ) : (
    <p className="muted">{empty}</p>
  );
}

function QualityGatesPanel({ room, status, checkpoints }) {
  const gates = buildQualityGates(room, status, checkpoints);
  return (
    <section className="panel-section quality-gates-panel">
      <h2>Quality gates</h2>
      <div className="quality-gates">
        {gates.map((gate) => (
          <div className={`quality-gate ${gate.status}`} key={gate.label}>
            {gate.status === "passed" ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
            <span>{gate.label}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function AgentScorecardsPanel({ status }) {
  const scorecards = buildAgentScorecards(status);
  return (
    <section className="panel-section scorecards-panel">
      <h2>Agent scorecards</h2>
      <div className="scorecard-list">
        {scorecards.length ? scorecards.map((card) => (
          <article className={`scorecard ${card.status}`} key={card.agent}>
            <div>
              <strong>{card.name}</strong>
              <span>{card.role} · {card.status}</span>
            </div>
            <b>{card.score}</b>
            <small>{formatNumber(card.tokens)} tokens</small>
          </article>
        )) : <p className="muted">Brak danych agentów dla scorecardów.</p>}
      </div>
    </section>
  );
}

function ArtifactList({ artifacts, empty }) {
  return artifacts?.length ? (
    <div className="artifact-list">
      {artifacts.map((artifact, index) => (
        <a
          key={`${artifact.artifact_path}-${index}`}
          href={`/artifact?path=${encodeURIComponent(artifact.artifact_path)}`}
          target="_blank"
          rel="noreferrer"
        >
          {displayAgentName({ name: artifact.agent }) || `artifact-${index + 1}`}
        </a>
      ))}
    </div>
  ) : (
    <p className="muted">{empty}</p>
  );
}

function collectArtifacts(status) {
  const seen = new Set();
  const artifacts = [];
  const fromStatus = Array.isArray(status?.artifacts) ? status.artifacts : [];
  const fromAgents = Object.values(status?.agents || {})
    .map((agent) =>
      agent?.artifact_path
        ? {
            agent: agent.name,
            artifact_path: agent.artifact_path
          }
        : null
    )
    .filter(Boolean);
  for (const artifact of [...fromStatus, ...fromAgents]) {
    if (!artifact?.artifact_path || seen.has(artifact.artifact_path)) continue;
    seen.add(artifact.artifact_path);
    artifacts.push(artifact);
  }
  return artifacts;
}

function agentArtifacts(status, agent) {
  return collectArtifacts(status).filter((artifact) => artifact.agent === agent?.name);
}

function roomArtifacts(status, room) {
  const agentNames = new Set((room?.agents || []).map((agent) => agent.name));
  return collectArtifacts(status).filter((artifact) => agentNames.has(artifact.agent));
}

function shortName(name) {
  return String(name)
    .split("_")
    .map((part) => part[0])
    .join("")
    .slice(0, 3)
    .toUpperCase();
}

function roomOutput(room) {
  return (room?.agents || [])
    .map((agent) => agent.summary || agent.error)
    .filter(Boolean)
    .join(" | ");
}

function belongsToRoom(checkpoint, role) {
  if (!role) return false;
  const node = String(checkpoint.node || "");
  if (role === "main") return node.includes("main") || node.includes("final");
  if (role === "analyst") return node.includes("analyst");
  if (role === "researcher") return node.includes("research");
  if (role === "builder") return node.includes("build");
  if (role === "reviewer") return node.includes("review");
  if (role === "learner") return node.includes("learn");
  if (role === "supervisor") return node.includes("supervisor");
  return false;
}

function belongsToAgent(checkpoint, agent) {
  if (!agent) return false;
  const node = String(checkpoint.node || "");
  const name = String(agent.name || "");
  if (node.includes(name)) return true;
  if (name === "main") return node.includes("main") || node.includes("final");
  if (name === "supervisor") return node.includes("supervisor");
  if (name === "builder") return node.includes("build");
  if (name === "self_learner") return node.includes("learn");
  if (name === "researcher") return node.includes("research");
  if (name === "reviewer") return node.includes("review");
  if (name.endsWith("_neutral")) return node.includes(agent.role);
  return false;
}

function isFailureEvent(event) {
  const name = String(event?.event || "").toLowerCase();
  return name.includes("failed") || name.includes("error");
}

function formatNumber(value) {
  return new Intl.NumberFormat("pl-PL").format(Number(value || 0));
}

function displayAgentName(agent) {
  if (!agent) return "-";
  const names = {
    main: "Main Communications Officer",
    supervisor: "Task Supervisor",
    analyst_positive: "Positive Analyst",
    analyst_negative: "Negative Analyst",
    analyst_neutral: "Neutral Analyst Arbiter",
    researcher_negative: "Research Critic",
    researcher: "Neutral Researcher Arbiter",
    builder: "Builder",
    reviewer_positive: "Positive Quality Reviewer",
    reviewer_negative: "Quality and Security Guardian",
    reviewer: "Neutral Review Arbiter",
    self_learner: "Self-Learning Quality Optimizer"
  };
  return agent.display_name || names[agent.name] || String(agent.name || "").replace(/_/g, " ");
}

function roomAssetFor(role, kind) {
  return ROOM_ASSETS[role] || (kind === "command" ? commandRoom : roomTile);
}

function agentAssetFor(agent) {
  const name = String(agent?.name || "");
  if (AGENT_ASSETS[name]) return AGENT_ASSETS[name];
  if (name.includes("analyst_positive")) return AGENT_ASSETS.analyst_positive;
  if (name.includes("analyst_negative")) return AGENT_ASSETS.analyst_negative;
  if (name.includes("analyst")) return AGENT_ASSETS.analyst_neutral;
  if (name.includes("researcher_negative")) return AGENT_ASSETS.researcher_negative;
  if (name.includes("research")) return AGENT_ASSETS.researcher;
  if (name.includes("reviewer_positive")) return AGENT_ASSETS.reviewer_positive;
  if (name.includes("reviewer_negative")) return AGENT_ASSETS.reviewer_negative;
  if (name.includes("review")) return AGENT_ASSETS.reviewer;
  if (name.includes("supervisor")) return AGENT_ASSETS.supervisor;
  if (name.includes("builder")) return AGENT_ASSETS.builder;
  if (name.includes("learner")) return AGENT_ASSETS.self_learner;
  if (name.includes("main")) return AGENT_ASSETS.main;
  return robotSprite;
}

function buildRunFlow(events, rooms, mode = "desktop", size = { width: 1000, height: 850 }, selected, onSelect, activeStep = null, flowSteps = null, onTownAction = null, runId = "") {
  const eventStatuses = {};
  for (const event of events || []) {
    const role = roleFromEvent(event);
    if (role) eventStatuses[role] = flowStatusFromEvent(event);
  }
  const agentStatuses = (rooms || []).flatMap((room) => room.agents || []).reduce((acc, agent) => {
    if (!agent?.role) return acc;
    acc[agent.role] = combineFlowStatus(acc[agent.role], normalizeFlowStatus(agent.status));
    return acc;
  }, eventStatuses);
  const steps = flowSteps || buildFlowSteps(events);
  const visibleSteps = activeStep ? steps.filter((step) => step.index <= activeStep) : steps;
  const firstRole = steps[0]?.target || "main";
  const lastRole = visibleSteps[visibleSteps.length - 1]?.target || steps[steps.length - 1]?.target || firstRole;
  const nodes = ["start", ...ROOMS.map((room) => room.role), "end"].map((role) => {
    const point = flowPoint(role, mode);
    const room = (rooms || []).find((item) => item.role === role) || ROOMS.find((item) => item.role === role);
    const status = role === "start" ? "running" : role === "end" ? normalizeFlowStatus(agentStatuses[lastRole] || "completed") : agentStatuses[role] || "idle";
    const label = role === "start" ? "START" : role === "end" ? "END" : room?.label || role;
    const subLabel = role === "start" ? firstRole : role === "end" ? lastRole : status;
    const kind = role === "start" || role === "end" ? role : room?.kind || "room";
    const roomAgents = room?.agents || [];
    const failedAgent = roomAgents.find((agent) => agent.status === "failed");
    return {
      id: role,
      type: "flowRoom",
      position: toReactFlowPosition(point, size, role),
      data: {
        label,
        subLabel,
        kind,
        status,
        agents: roomAgents,
        agentCount: roomAgents.length,
        active: roomAgents.some((agent) => agent.status === "running"),
        failedAgent,
        queueCount: roomQueueCount(room, events),
        selected: selected?.type === "room" && selected.id === role,
        onSelect,
        onTownAction,
        runId,
        role
      },
      draggable: false,
      selectable: false
    };
  });
  const edges = visibleSteps.map((transition) => {
    const status = normalizeFlowStatus(transition.status);
    const isActiveStep = transition.index === activeStep;
    const color = isActiveStep ? "#d6a400" : flowColor(status, transition.index - 1, visibleSteps.length);
    return {
      id: `${transition.source}-${transition.target}-${transition.index}`,
      source: transition.source,
      target: transition.target,
      label: transitionLabel(transition),
      type: "smoothstep",
      animated: status === "running",
      className: `flow-rf-edge ${status} ${isActiveStep ? "active-step" : ""}`,
      markerEnd: { type: MarkerType.ArrowClosed, color },
      style: {
        stroke: color,
        strokeWidth: isActiveStep ? 4.5 : 3.5,
        strokeDasharray: status === "completed" ? "10 7" : status === "running" ? "4 5" : "0"
      },
      labelStyle: { fill: color, fontWeight: 800, fontSize: 11 },
      labelBgStyle: { fill: "rgba(248,250,252,0.92)" },
      labelBgPadding: [5, 3],
      labelBgBorderRadius: 5
    };
  });
  return {
    nodes,
    edges,
    key: `${mode}-${size.width}-${size.height}-${activeStep}-${steps.map((step) => `${step.source}:${step.target}:${step.status}`).join("|")}`,
  };
}

function toReactFlowPosition(point, size, role) {
  const isTerminal = role === "start" || role === "end";
  return {
    x: (point.x / 100) * size.width - (isTerminal ? 58 : 82),
    y: (point.y / 100) * size.height - (isTerminal ? 24 : 67)
  };
}

function getFlowMode() {
  if (window.innerWidth <= 720) return "mobile";
  if (window.innerWidth <= 1120) return "tablet";
  return "desktop";
}

function flowPoint(role, mode) {
  const desktop = {
    start: { x: 8, y: 50 },
    end: { x: 92, y: 50 },
    analyst: { x: 31, y: 25 },
    supervisor: { x: 69, y: 25 },
    researcher: { x: 26, y: 50 },
    learner: { x: 74, y: 50 },
    builder: { x: 31, y: 75 },
    reviewer: { x: 69, y: 75 },
    main: { x: 50, y: 50 }
  };
  const tablet = {
    start: { x: 8, y: 46 },
    end: { x: 92, y: 46 },
    analyst: { x: 29, y: 20 },
    supervisor: { x: 71, y: 20 },
    researcher: { x: 24, y: 46 },
    learner: { x: 76, y: 46 },
    builder: { x: 31, y: 72 },
    reviewer: { x: 69, y: 72 },
    main: { x: 50, y: 46 }
  };
  const mobile = {
    start: { x: 16, y: 3 },
    end: { x: 84, y: 96 },
    analyst: { x: 50, y: 9 },
    supervisor: { x: 50, y: 24 },
    main: { x: 50, y: 39 },
    researcher: { x: 50, y: 55 },
    builder: { x: 50, y: 71 },
    reviewer: { x: 50, y: 82 },
    learner: { x: 50, y: 94 }
  };
  const points = mode === "mobile" ? mobile : mode === "tablet" ? tablet : desktop;
  return points[role] || desktop.main;
}

function normalizeFlowStatus(status) {
  const value = String(status || "").toLowerCase();
  if (value.includes("failed") || value.includes("error")) return "failed";
  if (value.includes("running") || value.includes("started")) return "running";
  if (value.includes("completed")) return "completed";
  return value || "idle";
}

function combineFlowStatus(current, next) {
  if (current === "failed" || next === "failed") return "failed";
  if (current === "running" || next === "running") return "running";
  if (current === "completed" || next === "completed") return "completed";
  return current || next || "idle";
}

function flowColor(status, index = 0, total = 1) {
  if (status === "failed") return "#c8322b";
  if (status === "running") return "#111923";
  return greenShade(index, total);
}

function transitionLabel(transition) {
  if (transition.status === "failed") return "błąd";
  if (transition.status === "running") return "w trakcie";
  return `${transition.index}. wykonano`;
}

createRoot(document.getElementById("root")).render(<App />);
