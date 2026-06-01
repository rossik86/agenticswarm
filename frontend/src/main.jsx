import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Handle, MarkerType, Position, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Activity,
  AlertTriangle,
  Boxes,
  CheckCircle2,
  Clock3,
  Play,
  RotateCcw,
  TerminalSquare,
  XCircle
} from "lucide-react";
import roomTile from "./assets/pixel-room.png";
import commandRoom from "./assets/pixel-command-room.png";
import robotSprite from "./assets/pixel-robot.png";
import "./styles.css";

const ROOMS = [
  { role: "analyst", label: "Analyst Council", x: 20, y: 20, kind: "council" },
  { role: "supervisor", label: "Supervisor Gate", x: 71, y: 20, kind: "single" },
  { role: "researcher", label: "Research Council", x: 20, y: 72, kind: "council" },
  { role: "builder", label: "Builder Bay", x: 48, y: 73, kind: "single" },
  { role: "reviewer", label: "Review Council", x: 77, y: 72, kind: "council" },
  { role: "main", label: "Main CO", x: 48, y: 43, kind: "command" }
];

const ROOM_AGENT_SLOTS = [
  { left: "22%", top: "56%" },
  { left: "49%", top: "62%" },
  { left: "68%", top: "50%" }
];

const FLOW_NODE_TYPES = { flowRoom: FlowRoomNode };

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
  const [notice, setNotice] = useState("");

  async function refresh() {
    const runQuery = selectedRunId ? `?run_id=${encodeURIComponent(selectedRunId)}` : "";
    const [statusResult, runsResult, eventsResult, checkpointsResult] = await Promise.all([
      fetch(`/status.json${runQuery}`, { cache: "no-store" }).then((response) => response.json()),
      fetch("/runs.json", { cache: "no-store" }).then((response) => response.json()),
      fetch(`/events.json${runQuery}`, { cache: "no-store" }).then((response) => response.json()),
      fetch(`/checkpoints.json${runQuery}`, { cache: "no-store" }).then((response) => response.json())
    ]);
    setStatus(statusResult);
    setRuns(runsResult.runs || []);
    setEvents((eventsResult.events || []).filter((event) => !statusResult.run_id || event.run_id === statusResult.run_id));
    setCheckpoints(checkpointsResult.checkpoints || []);
  }

  useEffect(() => {
    refresh().catch(() => setNotice("Nie mogę pobrać aktualnego statusu."));
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
        <RunStatus status={status} runs={runs} selectedRunId={selectedRunId} onSelectRun={setSelectedRunId} />
      </header>

      <section className="workspace">
        <OfficeMap rooms={rooms} onSelect={setSelected} selected={selected} events={events} agents={agents} />
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
            setNotice(`Pobieram ustawienia: ${displayAgentName(agent)}`);
            const settings = await fetch(`/agent-settings.json?agent=${encodeURIComponent(agent.name)}`, { cache: "no-store" }).then((item) =>
              item.json()
            );
            setAgentSettings(settings.agent);
            setNotice("");
          }}
        />
      </section>

      {notice ? (
        <button className="toast" type="button" onClick={() => setNotice("")}>
          {notice}
        </button>
      ) : null}
      {modal ? <TextModal modal={modal} onClose={() => setModal(null)} /> : null}
      {agentSettings ? <AgentSettingsModal settings={agentSettings} onClose={() => setAgentSettings(null)} /> : null}
    </main>
  );
}

function RunStatus({ status, runs, selectedRunId, onSelectRun }) {
  const state = status?.status || "waiting";
  const Icon = state === "completed" ? CheckCircle2 : state === "failed" ? XCircle : Activity;
  return (
    <div className={`run-status ${state}`}>
      <Icon size={18} />
      <span>{state}</span>
      <small>{status?.run_id || "no-run"}</small>
      <select value={selectedRunId} onChange={(event) => onSelectRun(event.target.value)} title="Wybierz run">
        <option value="">latest</option>
        {runs.map((run) => (
          <option value={run.run_id} key={run.run_id}>
            {run.run_id} · {run.status} · {compactOption(run.user_input) || "no input"}
            {" -> "}
            {compactOption(run.final_answer) || `${run.artifact_count || 0} md`}
          </option>
        ))}
      </select>
    </div>
  );
}

function OfficeMap({ rooms, onSelect, selected, events, agents }) {
  const officeRef = useRef(null);
  const [flowMode, setFlowMode] = useState(() => getFlowMode());
  const [officeSize, setOfficeSize] = useState({ width: 1000, height: 850 });
  useEffect(() => {
    const updateMode = () => setFlowMode(getFlowMode());
    window.addEventListener("resize", updateMode);
    return () => window.removeEventListener("resize", updateMode);
  }, []);
  useEffect(() => {
    if (!officeRef.current) return undefined;
    const observer = new ResizeObserver(([entry]) => {
      setOfficeSize({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    observer.observe(officeRef.current);
    return () => observer.disconnect();
  }, []);
  const flow = useMemo(
    () => buildRunFlow(events, rooms, flowMode, officeSize, selected, onSelect),
    [events, rooms, flowMode, officeSize, selected, onSelect]
  );
  return (
    <section className="office" aria-label="Agent town office" ref={officeRef}>
      <div className="corridor horizontal" />
      <div className="corridor vertical" />
      <div className="corridor diagonal-a" />
      <div className="corridor diagonal-b" />
      <RunFlowOverlay flow={flow} onSelect={onSelect} selected={selected} />
      <div className="legacy-rooms" aria-hidden="true">{rooms.map((room) => (
        <Room key={room.role} room={room} onSelect={onSelect} selected={selected} />
      ))}</div>
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
  const image = data.kind === "command" ? commandRoom : roomTile;
  return (
    <div className={`flow-rf-node ${data.kind || ""} ${data.status || ""}`}>
      <Handle id="in" type="target" position={Position.Left} className="flow-handle" />
      {data.kind === "start" || data.kind === "end" ? (
        <div className="flow-terminal">
          <strong>{data.label}</strong>
          {data.subLabel ? <span>{data.subLabel}</span> : null}
        </div>
      ) : (
        <div className={`flow-room-card ${data.selected ? "selected" : ""}`}>
          <span className="room-light" />
          <img src={image} alt="" className="room-art" />
          <span className="room-name">{data.label}</span>
          <span className="room-count">{data.agentCount}</span>
          {(data.agents || []).map((agent, index) => (
            <AgentSprite key={agent.name} agent={agent} slot={ROOM_AGENT_SLOTS[index % ROOM_AGENT_SLOTS.length]} onSelect={data.onSelect} />
          ))}
          {data.failedAgent ? <ErrorBubble agent={data.failedAgent} /> : data.active ? <SpeechBubble agents={data.agents} /> : null}
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
  const image = room.kind === "command" ? commandRoom : roomTile;

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
  return (
    <span
      className={`agent-sprite ${agent.status || "unknown"}`}
      style={slot}
      role="button"
      tabIndex={0}
      title={displayAgentName(agent)}
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
      <img src={robotSprite} alt="" />
      {agent.status === "failed" ? <span className="agent-error-mark">!</span> : null}
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

function SpeechBubble({ agents }) {
  const active = agents.find((agent) => agent.status === "running") || agents[0];
  const text = active?.summary || active?.error || "Analizuję następny krok...";
  return <span className="speech">{text.slice(0, 74)}</span>;
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
  onOpenAgentSettings
}) {
  if (selectedAgent) {
    const agentEvents = events.filter((event) => String(event.event || "").includes(selectedAgent.name));
    const agentCheckpoints = checkpoints.filter((checkpoint) => belongsToRoom(checkpoint, selectedAgent.role));
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
        <ArtifactLink path={selectedAgent.artifact_path} />
        <CheckpointList checkpoints={agentCheckpoints} onAction={onCheckpointAction} pendingCheckpoint={pendingCheckpoint} />
        <Timeline events={agentEvents} />
      </aside>
    );
  }

  const room = selectedRoom;
  const roomEvents = events.filter((event) => room?.agents?.some((agent) => String(event.event || "").includes(agent.name)));
  const roomCheckpoints = checkpoints.filter((checkpoint) => belongsToRoom(checkpoint, room?.role));
  return (
    <aside className="inspector">
      <PanelTitle icon={<Boxes size={17} />} title={room?.label || "Office"} subtitle={status?.run_id || "no-run"} />
      <CompactField label="Task" value={status?.user_input || status?.message || "-"} onOpen={onOpenText} />
      <CompactField label="Output" value={roomOutput(room) || status?.final_answer || "-"} onOpen={onOpenText} />
      <RunIOPanel status={status} onOpen={onOpenText} />
      <ResultPanel status={status} onOpen={onOpenText} />
      <TokenUsagePanel usage={status?.token_usage} selectedRole={room?.role} />
      <CouncilList room={room} />
      <CheckpointList checkpoints={roomCheckpoints} onAction={onCheckpointAction} pendingCheckpoint={pendingCheckpoint} />
      <Timeline events={roomEvents.length ? roomEvents : events.slice(-8)} />
    </aside>
  );
}

function AgentOptions({ agent, onOpenAgentSettings }) {
  return (
    <section className="agent-options">
      <button type="button" onClick={() => onOpenAgentSettings(agent)}>
        Ustawienia agenta
      </button>
      <span>{displayAgentName(agent)}</span>
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

function ResultPanel({ status, onOpen }) {
  const artifacts = collectArtifacts(status);
  const finalAnswer = status?.final_answer;
  return (
    <section className="panel-section result-panel">
      <h2>Wynik pracy</h2>
      {finalAnswer ? (
        <CompactField label="Final" value={finalAnswer} onOpen={onOpen} limit={180} />
      ) : (
        <p className="muted">Brak finalnej odpowiedzi dla aktualnego runa.</p>
      )}
      {artifacts.length ? (
        <div className="artifact-list">
          {artifacts.map((artifact, index) => (
            <a
              key={`${artifact.artifact_path}-${index}`}
              href={`/artifact?path=${encodeURIComponent(artifact.artifact_path)}`}
              target="_blank"
              rel="noreferrer"
            >
              {artifact.agent || `artifact-${index + 1}`}
            </a>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function TokenUsagePanel({ usage, selectedRole }) {
  const total = usage?.total_tokens || 0;
  const roles = usage?.by_role || {};
  const roleEntries = Object.entries(roles);
  return (
    <section className="panel-section token-panel">
      <h2>Token usage</h2>
      <div className="token-total">
        <strong>{formatNumber(total)}</strong>
        <span>{usage?.calls || 0} calls</span>
      </div>
      <div className="token-rooms">
        {roleEntries.length ? (
          roleEntries.map(([role, roleUsage]) => (
            <div className={`token-room ${role === selectedRole ? "selected" : ""}`} key={role}>
              <span>{role}</span>
              <strong>{formatNumber(roleUsage.total_tokens || 0)}</strong>
              <small>{roleUsage.calls || 0} calls</small>
            </div>
          ))
        ) : (
          <p className="muted">Brak danych token usage dla tego runu.</p>
        )}
      </div>
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

function AgentSettingsModal({ settings, onClose }) {
  const rows = [
    ["Agent", settings.name],
    ["Nazwa", settings.display_name],
    ["Typ", settings.type],
    ["Model", settings.model || "-"],
    ["Temperature", settings.temperature ?? "-"],
    ["Prompt", settings.prompt_path || "-"]
  ];
  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <section className="settings-modal" role="dialog" aria-modal="true" aria-label="Ustawienia agenta" onClick={(event) => event.stopPropagation()}>
        <header>
          <div>
            <h2>{settings.display_name || settings.name}</h2>
            <p>{settings.description || "Brak opisu."}</p>
          </div>
          <button type="button" onClick={onClose}>
            Zamknij
          </button>
        </header>
        <div className="settings-grid">
          <section>
            <h3>Konfiguracja</h3>
            {rows.map(([label, value]) => (
              <div className="kv-line" key={label}>
                <span>{label}</span>
                <strong>{String(value || "-")}</strong>
              </div>
            ))}
          </section>
          <section>
            <h3>Skills</h3>
            <TagList values={settings.skills || []} empty="Brak skills." />
            <h3>Tools</h3>
            <TagList values={settings.tools || []} empty="Brak tools." />
            <h3>Relacje</h3>
            <TagList values={[...(settings.delegates_to || []), ...(settings.validates || [])]} empty="Brak relacji." />
          </section>
        </div>
        <section className="prompt-section">
          <h3>Prompt</h3>
          <pre>{settings.prompt || "Brak promptu."}</pre>
        </section>
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

function ArtifactLink({ path }) {
  if (!path) return null;
  return (
    <a className="artifact-link" href={`/artifact?path=${encodeURIComponent(path)}`} target="_blank" rel="noreferrer">
      Otwórz artefakt
    </a>
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
  if (role === "supervisor") return node.includes("supervisor");
  return false;
}

function isFailureEvent(event) {
  const name = String(event?.event || "").toLowerCase();
  return name.includes("failed") || name.includes("error");
}

function formatNumber(value) {
  return new Intl.NumberFormat("pl-PL").format(Number(value || 0));
}

function compactOption(value) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length > 42 ? `${text.slice(0, 42)}...` : text;
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
    reviewer: "Neutral Review Arbiter"
  };
  return agent.display_name || names[agent.name] || String(agent.name || "").replace(/_/g, " ");
}

function buildRunFlow(events, rooms, mode = "desktop", size = { width: 1000, height: 850 }, selected, onSelect) {
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
  const sequence = [];
  let previousRole = null;
  for (const event of events || []) {
    const role = roleFromEvent(event);
    if (!role) continue;
    if (previousRole !== role) sequence.push(role);
    previousRole = role;
  }
  const transitions = [];
  if (sequence.length) {
    transitions.push({ source: "start", target: sequence[0], status: agentStatuses[sequence[0]] || "running" });
    for (let index = 1; index < sequence.length; index += 1) {
      transitions.push({ source: sequence[index - 1], target: sequence[index], status: agentStatuses[sequence[index]] || "running" });
    }
    transitions.push({ source: sequence[sequence.length - 1], target: "end", status: agentStatuses[sequence[sequence.length - 1]] || "completed" });
  }
  const firstRole = sequence[0] || "main";
  const lastRole = sequence[sequence.length - 1] || firstRole;
  const latestByPair = new Map();
  transitions.forEach((transition, index) => {
    latestByPair.set(`${transition.source}->${transition.target}`, { ...transition, index });
  });
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
        selected: selected?.type === "room" && selected.id === role,
        onSelect
      },
      draggable: false,
      selectable: false
    };
  });
  const transitionList = Array.from(latestByPair.values());
  const edges = transitionList.map((transition) => ({
    id: `${transition.source}-${transition.target}-${transition.index}`,
    source: transition.source,
    target: transition.target,
    label: transitionLabel(transition),
    type: "smoothstep",
    animated: normalizeFlowStatus(transition.status) === "running",
    className: `flow-rf-edge ${normalizeFlowStatus(transition.status)}`,
    markerEnd: { type: MarkerType.ArrowClosed, color: flowColor(transition.status) },
    style: {
      stroke: flowColor(transition.status),
      strokeWidth: 3,
      strokeDasharray: normalizeFlowStatus(transition.status) === "completed" ? "8 6" : normalizeFlowStatus(transition.status) === "running" ? "4 5" : "0"
    },
    labelStyle: { fill: flowColor(transition.status), fontWeight: 800, fontSize: 11 },
    labelBgStyle: { fill: "rgba(248,250,252,0.92)" },
    labelBgPadding: [5, 3],
    labelBgBorderRadius: 5
  }));
  return {
    nodes,
    edges,
    key: `${mode}-${size.width}-${size.height}-${sequence.join("-")}-${edges.map((edge) => `${edge.source}:${edge.target}:${edge.className}`).join("|")}`,
  };
}

function toReactFlowPosition(point, size, role) {
  const isTerminal = role === "start" || role === "end";
  return {
    x: (point.x / 100) * size.width - (isTerminal ? 58 : 119),
    y: (point.y / 100) * size.height - (isTerminal ? 24 : 98)
  };
}

function getFlowMode() {
  if (window.innerWidth <= 720) return "mobile";
  if (window.innerWidth <= 1120) return "tablet";
  return "desktop";
}

function flowPoint(role, mode) {
  const desktop = {
    start: { x: 6, y: 43 },
    end: { x: 94, y: 43 },
    analyst: { x: 20, y: 20 },
    supervisor: { x: 71, y: 20 },
    researcher: { x: 20, y: 72 },
    builder: { x: 48, y: 73 },
    reviewer: { x: 77, y: 72 },
    main: { x: 48, y: 43 }
  };
  const tablet = {
    start: { x: 8, y: 35 },
    end: { x: 92, y: 35 },
    analyst: { x: 27, y: 13 },
    supervisor: { x: 73, y: 13 },
    main: { x: 50, y: 35 },
    researcher: { x: 26, y: 63 },
    builder: { x: 50, y: 80 },
    reviewer: { x: 74, y: 63 }
  };
  const mobile = {
    start: { x: 16, y: 3 },
    end: { x: 84, y: 96 },
    analyst: { x: 50, y: 9 },
    supervisor: { x: 50, y: 24 },
    main: { x: 50, y: 39 },
    researcher: { x: 50, y: 55 },
    builder: { x: 50, y: 71 },
    reviewer: { x: 50, y: 87 }
  };
  const points = mode === "mobile" ? mobile : mode === "tablet" ? tablet : desktop;
  return points[role] || desktop.main;
}

function roleFromEvent(event) {
  const name = String(event?.event || "").toLowerCase();
  if (!name.startsWith("agent.")) return null;
  if (name.includes("analyst")) return "analyst";
  if (name.includes("research")) return "researcher";
  if (name.includes("build") || name.includes("builder")) return "builder";
  if (name.includes("review")) return "reviewer";
  if (name.includes("supervisor")) return "supervisor";
  if (name.includes("main") || name.includes("final")) return "main";
  return null;
}

function flowStatusFromEvent(event) {
  const name = String(event?.event || "").toLowerCase();
  if (name.includes("failed") || name.includes("error")) return "failed";
  if (name.includes("started") || name.includes("running")) return "running";
  return "completed";
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

function flowColor(status) {
  if (status === "failed") return "#c8322b";
  if (status === "running") return "#111923";
  return "#2f9d58";
}

function transitionLabel(transition) {
  if (transition.status === "failed") return "błąd";
  if (transition.status === "running") return "w trakcie";
  return "wykonano";
}

createRoot(document.getElementById("root")).render(<App />);
