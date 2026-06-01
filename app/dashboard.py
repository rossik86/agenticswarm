from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import html
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sqlite3
import threading
from urllib.parse import parse_qs, quote, urlparse
from zoneinfo import ZoneInfo

import yaml

from app.agents.runner import load_skill_markdowns
from app.config.loader import load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the Multiagent Swarm dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--config",
        default="configs/agents.yaml",
        help="Path to the agents configuration file, relative to the project root unless absolute.",
    )
    return parser


def serve_dashboard(project_root: Path, config_path: Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    config = load_config(config_path)
    artifact_root = project_root / config.artifact_root
    events_path = artifact_root / "events.jsonl"
    checkpoint_path = project_root / config.checkpoint.path
    frontend_dist = project_root / "frontend" / "dist"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_html(render_dashboard(read_latest_status(artifact_root), read_recent_events(events_path)))
                return
            if parsed.path == "/town":
                index_path = frontend_dist / "index.html"
                if index_path.exists():
                    self._send_file(index_path, "text/html; charset=utf-8")
                    return
                self._send_html(render_town(read_latest_status(artifact_root), read_recent_events(events_path)))
                return
            if parsed.path.startswith("/assets/"):
                self._send_static_asset(frontend_dist, parsed.path)
                return
            if parsed.path == "/status.json":
                params = parse_qs(parsed.query)
                run_id = params.get("run_id", [None])[0]
                self._send_json(read_status(artifact_root, run_id) if run_id else read_latest_status(artifact_root))
                return
            if parsed.path == "/runs.json":
                self._send_json({"runs": read_runs(artifact_root)})
                return
            if parsed.path == "/agent-settings.json":
                params = parse_qs(parsed.query)
                agent_name = params.get("agent", [""])[0]
                self._send_json({"agent": read_agent_settings(project_root, config, agent_name)})
                return
            if parsed.path == "/events.json":
                params = parse_qs(parsed.query)
                self._send_json({"events": read_recent_events(events_path, limit=300, run_id=params.get("run_id", [None])[0])})
                return
            if parsed.path == "/checkpoints.json":
                params = parse_qs(parsed.query)
                self._send_json(
                    {
                        "checkpoints": read_checkpoints(
                            checkpoint_path,
                            run_id=params.get("run_id", [None])[0],
                        )
                    }
                )
                return
            if parsed.path == "/artifact":
                params = parse_qs(parsed.query)
                target = params.get("path", [""])[0]
                self._send_artifact(artifact_root, target)
                return
            self.send_error(404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/agent-settings.json":
                payload = self._read_json_body()
                result = update_agent_runtime_settings(config_path, payload)
                if result.get("updated"):
                    nonlocal config
                    config = load_config(config_path)
                    agent_name = str(payload.get("agent") or "")
                    result["agent"] = read_agent_settings(project_root, config, agent_name)
                self._send_json(result)
                return
            if parsed.path in {"/checkpoint/resume", "/checkpoint/restart"}:
                payload = self._read_json_body()
                action = parsed.path.rsplit("/", 1)[-1]
                checkpoint = read_checkpoint(checkpoint_path, int(payload.get("checkpoint_id", 0) or 0))
                if not checkpoint:
                    self._send_json(
                        {
                            "accepted": False,
                            "action": action,
                            "message": "Nie znaleziono checkpointu do uruchomienia.",
                        }
                    )
                    return
                action_record = append_checkpoint_action(project_root / "workspace" / "checkpoint_actions.jsonl", action, payload)
                prompt = build_checkpoint_prompt(action, checkpoint)
                start_checkpoint_run(project_root, config_path, prompt, action_record["id"])
                self._send_json(
                    {
                        "accepted": True,
                        "action": action,
                        "message": f"Checkpoint {action} uruchomiony w tle.",
                    }
                )
                return
            self.send_error(404)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _read_json_body(self) -> dict[str, object]:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                return {}
            try:
                return json.loads(self.rfile.read(length).decode("utf-8"))
            except json.JSONDecodeError:
                return {}

        def _send_html(self, body: str) -> None:
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, body: dict[str, object]) -> None:
            data = json.dumps(body, ensure_ascii=True, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_file(self, path: Path, content_type: str | None = None) -> None:
            if not path.exists() or not path.is_file():
                self.send_error(404)
                return
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_static_asset(self, frontend_dist: Path, request_path: str) -> None:
            target = (frontend_dist / request_path.lstrip("/")).resolve()
            root = frontend_dist.resolve()
            if root not in target.parents and target != root:
                self.send_error(403)
                return
            self._send_file(target)

        def _send_artifact(self, artifact_root: Path, target: str) -> None:
            try:
                path = Path(target).resolve()
                root = artifact_root.resolve()
            except OSError:
                self.send_error(400)
                return
            if root not in path.parents and path != root:
                self.send_error(403)
                return
            if not path.exists() or not path.is_file():
                self.send_error(404)
                return
            data = path.read_text(encoding="utf-8", errors="replace").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Dashboard: http://{host}:{port}")
    server.serve_forever()


def read_latest_status(artifact_root: Path) -> dict[str, object]:
    path = artifact_root / "latest.json"
    if not path.exists():
        return {
            "status": "waiting",
            "message": "No runs yet.",
            "agents": {},
            "artifacts": [],
            "errors": [],
        }
    status = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(status, dict) and status.get("run_id"):
        status.setdefault("path", str(artifact_root / str(status["run_id"])))
    return status


def read_status(artifact_root: Path, run_id: str | None) -> dict[str, object]:
    if not run_id:
        return read_latest_status(artifact_root)
    run_dir = (artifact_root / run_id).resolve()
    root = artifact_root.resolve()
    if root not in run_dir.parents and run_dir != root:
        return {"status": "not_found", "message": "Run not found.", "agents": {}, "artifacts": [], "errors": []}
    status_path = run_dir / "status.json"
    if status_path.exists():
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if isinstance(status, dict):
            status.setdefault("path", str(run_dir))
        return status
    if run_dir.exists() and run_dir.is_dir():
        artifacts = [
            {"agent": path.stem, "status": "completed", "artifact_path": str(path), "summary": path.name}
            for path in sorted(run_dir.glob("*.md"))
        ]
        return {
            "run_id": run_id,
            "status": "artifact_only",
            "user_input": "",
            "started_at": None,
            "updated_at": _path_timestamp(run_dir),
            "finished_at": None,
            "agents": {},
            "artifacts": artifacts,
            "roles": {},
            "errors": [],
            "final_answer": None,
            "path": str(run_dir),
        }
    return {"run_id": run_id, "status": "not_found", "message": "Run not found.", "agents": {}, "artifacts": [], "errors": []}


def read_runs(artifact_root: Path, limit: int = 80) -> list[dict[str, object]]:
    if not artifact_root.exists():
        return []
    runs = []
    for run_dir in sorted((path for path in artifact_root.iterdir() if path.is_dir()), key=lambda path: path.stat().st_mtime, reverse=True):
        status_path = run_dir / "status.json"
        status = {}
        if status_path.exists():
            try:
                status = json.loads(status_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                status = {}
        markdown_count = len(list(run_dir.glob("*.md")))
        runs.append(
            {
                "run_id": run_dir.name,
                "status": status.get("status", "artifact_only" if markdown_count else "unknown"),
                "user_input": status.get("user_input", ""),
                "final_answer": status.get("final_answer"),
                "started_at": status.get("started_at"),
                "updated_at": status.get("updated_at") or _path_timestamp(run_dir),
                "artifact_count": len(status.get("artifacts", [])) if isinstance(status.get("artifacts"), list) else markdown_count,
                "path": str(run_dir),
            }
        )
        if len(runs) >= limit:
            break
    return runs


def read_agent_settings(project_root: Path, config: object, agent_name: str) -> dict[str, object]:
    agents = getattr(config, "agents", {})
    agent = agents.get(agent_name) if isinstance(agents, dict) else None
    if not agent:
        return {"name": agent_name, "status": "not_found", "prompt": "", "skills": [], "skill_markdowns": [], "tools": []}
    prompt_path = getattr(agent, "prompt", None)
    prompt_text = ""
    if prompt_path:
        path = (project_root / prompt_path).resolve()
        root = project_root.resolve()
        if (root in path.parents or path == root) and path.exists() and path.is_file():
            prompt_text = path.read_text(encoding="utf-8")
    provider = getattr(agent, "provider", None)
    defaults = getattr(config, "defaults", None)
    effective_provider = provider or getattr(defaults, "provider", None)
    effective_model = getattr(agent, "model", None) or getattr(defaults, "model", None)
    return {
        "name": agent_name,
        "display_name": getattr(agent, "display_name", None) or agent_name.replace("_", " ").title(),
        "description": getattr(agent, "description", ""),
        "type": getattr(agent, "type", ""),
        "provider": provider,
        "effective_provider": effective_provider,
        "skills": getattr(agent, "skills", []),
        "skill_markdowns": load_skill_markdowns(project_root, getattr(agent, "skills", [])),
        "tools": getattr(agent, "tools", []),
        "delegates_to": getattr(agent, "delegates_to", []),
        "validates": getattr(agent, "validates", []),
        "model": getattr(agent, "model", None),
        "effective_model": effective_model,
        "model_options": model_options_for_provider(str(effective_provider or "")),
        "temperature": getattr(agent, "temperature", None),
        "prompt_path": str(prompt_path) if prompt_path else "",
        "prompt": prompt_text,
    }


def update_agent_runtime_settings(config_path: Path, payload: dict[str, object]) -> dict[str, object]:
    agent_name = str(payload.get("agent") or "").strip()
    if not agent_name:
        return {"updated": False, "message": "Brak nazwy agenta."}
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    agents = raw.get("agents")
    if not isinstance(agents, dict) or agent_name not in agents:
        return {"updated": False, "message": "Nie znaleziono agenta."}
    agent = agents[agent_name]
    if not isinstance(agent, dict):
        return {"updated": False, "message": "Niepoprawna konfiguracja agenta."}

    provider_value = payload.get("provider")
    if provider_value in {"", None, "default"}:
        agent.pop("provider", None)
    elif provider_value in {"agents_sdk", "codex_cli", "openhands"}:
        agent["provider"] = str(provider_value)
    else:
        return {"updated": False, "message": "Nieobsługiwany provider."}

    model_value = str(payload.get("model") or "").strip()
    if model_value:
        agent["model"] = model_value
    else:
        agent.pop("model", None)

    temperature_value = payload.get("temperature")
    if temperature_value in {"", None}:
        agent.pop("temperature", None)
    else:
        try:
            agent["temperature"] = float(temperature_value)
        except (TypeError, ValueError):
            return {"updated": False, "message": "Temperature musi być liczbą."}

    config_path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=False), encoding="utf-8")
    load_config(config_path)
    return {"updated": True, "message": "Ustawienia agenta zapisane."}


def model_options_for_provider(provider: str) -> list[str]:
    options: dict[str, list[str]] = {
        "agents_sdk": ["gpt-4.1", "gpt-4.1-mini", "o4-mini", "o3"],
        "codex_cli": ["gpt-5", "gpt-5-codex", "gpt-4.1", "o4-mini"],
        "openhands": ["gpt-4.1", "gpt-4.1-mini", "claude-sonnet-4", "local"],
    }
    return options.get(provider, [])


def _path_timestamp(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, ZoneInfo("Europe/Warsaw")).isoformat(timespec="seconds")


def read_recent_events(path: Path, limit: int = 30, run_id: str | None = None) -> list[dict[str, object]]:
    if not path.exists():
        return []
    events = []
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if run_id and event.get("run_id") != run_id:
            continue
        events.append(event)
        if len(events) >= limit:
            break
    return list(reversed(events))


def read_checkpoints(path: Path, run_id: str | None = None, limit: int = 80) -> list[dict[str, object]]:
    if not path.exists():
        return []
    query = "select id, run_id, node, state_json, created_at from checkpoints"
    params: tuple[object, ...] = ()
    if run_id:
        query += " where run_id = ?"
        params = (run_id,)
    query += " order by id desc limit ?"
    params = (*params, limit)
    with sqlite3.connect(path) as conn:
        rows = conn.execute(query, params).fetchall()
    checkpoints = []
    for checkpoint_id, checkpoint_run_id, node, state_json, created_at in rows:
        state = parse_checkpoint_state(state_json)
        checkpoints.append(
            {
                "id": checkpoint_id,
                "run_id": checkpoint_run_id,
                "node": node,
                "created_at": created_at,
                "state_keys": sorted(state.keys()) if isinstance(state, dict) else [],
                "error": state.get("error") if isinstance(state, dict) else None,
            }
        )
    return checkpoints


def read_checkpoint(path: Path, checkpoint_id: int) -> dict[str, object] | None:
    if not checkpoint_id or not path.exists():
        return None
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "select id, run_id, node, state_json, created_at from checkpoints where id = ?",
            (checkpoint_id,),
        ).fetchone()
    if not row:
        return None
    checkpoint_id, checkpoint_run_id, node, state_json, created_at = row
    state = parse_checkpoint_state(state_json)
    return {
        "id": checkpoint_id,
        "run_id": checkpoint_run_id,
        "node": node,
        "created_at": created_at,
        "state": state,
        "state_keys": sorted(state.keys()) if isinstance(state, dict) else [],
        "error": state.get("error") if isinstance(state, dict) else None,
    }


def parse_checkpoint_state(payload: str) -> dict[str, object]:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def append_checkpoint_action(path: Path, action: str, payload: dict[str, object]) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"id": _timestamp_id(), "action": action, "payload": payload, "created_at": _timestamp()}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")
    return record


def build_checkpoint_prompt(action: str, checkpoint: dict[str, object]) -> str:
    state = checkpoint.get("state")
    state_dict = state if isinstance(state, dict) else {}
    user_input = str(state_dict.get("user_input") or "")
    errors = state_dict.get("errors") if isinstance(state_dict.get("errors"), list) else []
    artifacts = state_dict.get("artifacts") if isinstance(state_dict.get("artifacts"), list) else []
    quality = state_dict.get("quality_result") or state_dict.get("review_result")
    build = state_dict.get("build_result")
    if action == "resume":
        action_instruction = (
            "Kontynuuj proces od tego checkpointu. Nie powtarzaj ukończonych kroków bez potrzeby; "
            "skup się na doprowadzeniu zadania do finalnej odpowiedzi."
        )
    else:
        action_instruction = (
            "Uruchom od nowa etap review dla tego checkpointu. Skup się na naprawie/przejściu problemu review, "
            "zweryfikuj jakość i oddaj wynik do supervisora."
        )
    context = {
        "checkpoint": {
            "id": checkpoint.get("id"),
            "run_id": checkpoint.get("run_id"),
            "node": checkpoint.get("node"),
            "created_at": checkpoint.get("created_at"),
        },
        "original_user_input": user_input,
        "action": action,
        "errors": errors[-3:],
        "artifacts": artifacts[-10:],
        "build_result": build,
        "quality_result": quality,
    }
    return (
        "To jest automatyczne wznowienie zadania z checkpointu w dashboardzie.\n\n"
        f"Instrukcja: {action_instruction}\n\n"
        "Zachowaj kontekst poprzedniego przebiegu, nie ignoruj błędów i wygeneruj nowy artefakt/odpowiedź, "
        "który jasno pokazuje co zostało wznowione albo zrestartowane.\n\n"
        "Kontekst checkpointu JSON:\n"
        f"{json.dumps(context, ensure_ascii=True, indent=2)}"
    )


def start_checkpoint_run(project_root: Path, config_path: Path, prompt: str, action_id: object) -> None:
    def worker() -> None:
        from app.main import SwarmApp

        try:
            app = SwarmApp(project_root, config_path, provider_override="codex_cli")
            app.config.defaults.provider = "codex_cli"
            for agent_config in app.config.agents.values():
                agent_config.provider = "codex_cli"
            append_checkpoint_debug(
                project_root / "workspace" / "checkpoint_action_debug.jsonl",
                action_id,
                {
                    "default_provider": app.config.defaults.provider,
                    "main_provider": app.config.agents["main"].provider,
                },
            )
            asyncio.run(app.run_turn(prompt))
        except Exception as exc:
            error_path = project_root / "workspace" / "checkpoint_action_errors.jsonl"
            error_path.parent.mkdir(parents=True, exist_ok=True)
            with error_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {"action_id": action_id, "error": str(exc), "created_at": _timestamp()},
                        ensure_ascii=True,
                    )
                    + "\n"
                )

    thread = threading.Thread(target=worker, name=f"checkpoint-action-{action_id}", daemon=True)
    thread.start()


def _timestamp_id() -> str:
    return datetime.now(ZoneInfo("Europe/Warsaw")).strftime("%Y%m%d-%H%M%S-%f")


def _timestamp() -> str:
    return datetime.now(ZoneInfo("Europe/Warsaw")).isoformat(timespec="seconds")


def append_checkpoint_debug(path: Path, action_id: object, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"action_id": action_id, **data, "created_at": _timestamp()}, ensure_ascii=True) + "\n")


def render_dashboard(status: dict[str, object], events: list[dict[str, object]] | None = None) -> str:
    agents = status.get("agents", {})
    artifacts = status.get("artifacts", [])
    errors = status.get("errors", [])
    final_answer = status.get("final_answer") or ""
    agent_rows = "\n".join(render_agent_row(agent) for agent in agents.values()) if isinstance(agents, dict) else ""
    agent_map = render_agent_map(agents) if isinstance(agents, dict) else ""
    artifact_rows = "\n".join(render_artifact_row(artifact) for artifact in artifacts) if isinstance(artifacts, list) else ""
    error_rows = "\n".join(f"<li>{html.escape(str(error))}</li>" for error in errors) if isinstance(errors, list) else ""
    event_rows = "\n".join(render_event_row(event) for event in (events or []))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="5">
  <title>Multiagent Swarm Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Segoe UI, Arial, sans-serif;
      background: #f5f7fb;
      color: #20242c;
    }}
    body {{ margin: 0; }}
    header {{ background: #16202a; color: #fff; padding: 18px 24px; }}
    main {{ max-width: 1160px; margin: 0 auto; padding: 22px; }}
    h1 {{ font-size: 22px; margin: 0 0 6px; font-weight: 650; }}
    h2 {{ font-size: 16px; margin: 24px 0 10px; }}
    .meta {{ color: #c8d1dc; font-size: 13px; }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-top: 16px;
    }}
    .metric {{ background: #fff; border: 1px solid #dde3ec; border-radius: 8px; padding: 12px; }}
    .label {{ color: #667083; font-size: 12px; text-transform: uppercase; }}
    .value {{ font-size: 18px; margin-top: 4px; overflow-wrap: anywhere; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #dde3ec; }}
    th, td {{ text-align: left; padding: 10px; border-bottom: 1px solid #e9eef5; vertical-align: top; }}
    th {{ font-size: 12px; color: #536174; background: #f9fbfe; text-transform: uppercase; }}
    .badge {{ display: inline-block; min-width: 82px; text-align: center; border-radius: 999px; padding: 3px 9px; font-size: 12px; }}
    .agent-map {{ display: grid; grid-template-columns: repeat(3, minmax(180px, 1fr)); gap: 12px; margin: 10px 0 16px; }}
    .role-group {{ background: #eef3f8; border: 1px solid #d7e0eb; border-radius: 8px; padding: 10px; }}
    .role-title {{ font-weight: 700; margin-bottom: 8px; text-transform: capitalize; }}
    .agent-node {{ background: #fff; border: 1px solid #dde3ec; border-top: 4px solid #8a96a8; border-radius: 8px; padding: 12px; min-height: 72px; }}
    .agent-node.running {{ border-top-color: #d19a00; }}
    .agent-node.completed {{ border-top-color: #2e9d57; }}
    .agent-node.failed {{ border-top-color: #c33b32; }}
    .agent-name {{ font-weight: 650; margin-bottom: 6px; }}
    .running {{ background: #fff0c2; color: #705100; }}
    .completed {{ background: #dff6e8; color: #145c32; }}
    .failed {{ background: #ffe1df; color: #8b1d16; }}
    .idle, .waiting, .unknown {{ background: #e9eef5; color: #465367; }}
    pre {{ white-space: pre-wrap; background: #fff; border: 1px solid #dde3ec; border-radius: 8px; padding: 12px; }}
    a {{ color: #165dcc; text-decoration: none; }}
    @media (max-width: 760px) {{ .summary {{ grid-template-columns: 1fr; }} table {{ font-size: 13px; }} }}
  </style>
</head>
<body>
  <header>
    <h1>Multiagent Swarm Dashboard</h1>
    <div class="meta">Auto refresh every 5 seconds | <a href="/town">AI Town view</a></div>
  </header>
  <main>
    <section class="summary">
      {metric("Run", status.get("run_id", "-"))}
      {metric("Status", status.get("status", "-"))}
      {metric("Started", status.get("started_at", "-"))}
      {metric("Updated", status.get("updated_at", "-"))}
    </section>
    <h2>Request</h2>
    <pre>{html.escape(str(status.get("user_input", status.get("message", ""))))}</pre>
    <h2>Agents</h2>
    <div class="agent-map">{agent_map}</div>
    <table>
      <thead><tr><th>Agent</th><th>Status</th><th>Started</th><th>Finished</th><th>Summary</th><th>Artifact</th></tr></thead>
      <tbody>{agent_rows or '<tr><td colspan="6">No agent state yet.</td></tr>'}</tbody>
    </table>
    <h2>Artifacts</h2>
    <table>
      <thead><tr><th>Agent</th><th>Summary</th><th>Path</th></tr></thead>
      <tbody>{artifact_rows or '<tr><td colspan="3">No artifacts yet.</td></tr>'}</tbody>
    </table>
    <h2>Final Answer</h2>
    <pre>{html.escape(str(final_answer))}</pre>
    <h2>Errors</h2>
    <ul>{error_rows or '<li>No errors.</li>'}</ul>
    <h2>Recent Events</h2>
    <table>
      <thead><tr><th>Time</th><th>Run</th><th>Event</th><th>Data</th></tr></thead>
      <tbody>{event_rows or '<tr><td colspan="4">No events yet.</td></tr>'}</tbody>
    </table>
  </main>
</body>
</html>"""


def render_town(status: dict[str, object], events: list[dict[str, object]] | None = None) -> str:
    agents = status.get("agents", {})
    town = render_town_map(agents) if isinstance(agents, dict) else ""
    event_feed = "\n".join(render_town_event(event) for event in (events or [])[-12:])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="5">
  <title>Multiagent Swarm Town</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Segoe UI, Arial, sans-serif;
      background: #eef2f6;
      color: #20242c;
    }}
    body {{ margin: 0; }}
    header {{ background: #17212b; color: #fff; padding: 16px 22px; }}
    header a {{ color: #dce8ff; }}
    h1 {{ font-size: 22px; margin: 0 0 5px; }}
    .meta {{ color: #c7d2df; font-size: 13px; }}
    main {{ display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 18px; max-width: 1360px; margin: 0 auto; padding: 18px; }}
    .town {{
      position: relative;
      min-height: 760px;
      border: 1px solid #cfdae6;
      border-radius: 8px;
      overflow: hidden;
      background:
        linear-gradient(90deg, rgba(255,255,255,.55) 1px, transparent 1px) 0 0 / 48px 48px,
        linear-gradient(0deg, rgba(255,255,255,.55) 1px, transparent 1px) 0 0 / 48px 48px,
        #dfe8f1;
    }}
    .road-horizontal, .road-vertical {{
      position: absolute;
      background: #bac8d6;
      box-shadow: inset 0 0 0 1px rgba(70,83,103,.14);
    }}
    .road-horizontal {{ left: 0; right: 0; top: 360px; height: 68px; }}
    .road-vertical {{ top: 0; bottom: 0; left: 50%; width: 68px; transform: translateX(-50%); }}
    .plaza {{
      position: absolute;
      left: 50%;
      top: 394px;
      width: 132px;
      height: 132px;
      transform: translate(-50%, -50%);
      background: #f6f8fb;
      border: 1px solid #bdcad8;
      border-radius: 8px;
      display: grid;
      place-items: center;
      text-align: center;
      font-weight: 700;
      color: #465367;
    }}
    .building {{
      position: absolute;
      width: 250px;
      min-height: 158px;
      background: #fff;
      border: 1px solid #cbd8e5;
      border-radius: 8px;
      box-shadow: 0 10px 28px rgba(34,48,66,.11);
      padding: 12px;
    }}
    .building.main {{ left: 24px; top: 34px; }}
    .building.analyst {{ left: 350px; top: 34px; }}
    .building.supervisor {{ right: 24px; top: 34px; }}
    .building.researcher {{ left: 24px; bottom: 42px; }}
    .building.builder {{ left: 350px; bottom: 42px; }}
    .building.reviewer {{ right: 24px; bottom: 42px; }}
    .building-title {{ font-size: 14px; font-weight: 750; text-transform: uppercase; color: #465367; margin-bottom: 9px; }}
    .avatars {{ display: flex; flex-wrap: wrap; gap: 9px; align-items: flex-start; }}
    .avatar {{
      width: 66px;
      min-height: 88px;
      display: grid;
      justify-items: center;
      gap: 5px;
      color: #20242c;
      font-size: 11px;
      text-align: center;
    }}
    .head {{
      width: 42px;
      height: 42px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      font-weight: 800;
      border: 3px solid #8a96a8;
      background: #f9fbfe;
    }}
    .avatar.running .head {{ border-color: #d19a00; background: #fff4cf; }}
    .avatar.completed .head {{ border-color: #2e9d57; background: #e3f8eb; }}
    .avatar.failed .head {{ border-color: #c33b32; background: #ffe6e3; }}
    .avatar.stopped .head {{ border-color: #6e7888; background: #eef1f5; }}
    .stance {{ color: #667083; text-transform: uppercase; font-size: 10px; }}
    .agent-label {{ overflow-wrap: anywhere; }}
    aside {{ display: flex; flex-direction: column; gap: 12px; }}
    .panel {{ background: #fff; border: 1px solid #d8e1eb; border-radius: 8px; padding: 12px; }}
    .panel h2 {{ font-size: 15px; margin: 0 0 10px; }}
    .kv {{ display: grid; grid-template-columns: 86px 1fr; gap: 6px; font-size: 13px; }}
    .key {{ color: #667083; }}
    .events {{ display: grid; gap: 8px; }}
    .event {{ border-left: 3px solid #8a96a8; padding-left: 8px; font-size: 12px; }}
    .event strong {{ display: block; font-size: 12px; }}
    .request {{ white-space: pre-wrap; font-size: 13px; }}
    @media (max-width: 980px) {{
      main {{ grid-template-columns: 1fr; }}
      .town {{ min-height: 1120px; }}
      .building {{ position: relative; left: auto !important; right: auto !important; top: auto !important; bottom: auto !important; margin: 14px; width: auto; }}
      .road-horizontal, .road-vertical, .plaza {{ display: none; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Multiagent Swarm Town</h1>
    <div class="meta">Role city view | Auto refresh every 5 seconds | <a href="/">table dashboard</a></div>
  </header>
  <main>
    <section class="town">
      <div class="road-horizontal"></div>
      <div class="road-vertical"></div>
      <div class="plaza">Supervisor<br>Gate</div>
      {town}
    </section>
    <aside>
      <section class="panel">
        <h2>Run</h2>
        <div class="kv">
          <div class="key">ID</div><div>{html.escape(str(status.get("run_id", "-")))}</div>
          <div class="key">Status</div><div>{html.escape(str(status.get("status", "-")))}</div>
          <div class="key">Started</div><div>{html.escape(str(status.get("started_at", "-")))}</div>
          <div class="key">Updated</div><div>{html.escape(str(status.get("updated_at", "-")))}</div>
        </div>
      </section>
      <section class="panel">
        <h2>Request</h2>
        <div class="request">{html.escape(str(status.get("user_input", status.get("message", ""))))}</div>
      </section>
      <section class="panel">
        <h2>Event Feed</h2>
        <div class="events">{event_feed or '<div class="event">No events yet.</div>'}</div>
      </section>
    </aside>
  </main>
</body>
</html>"""


def metric(label: str, value: object) -> str:
    return f'<div class="metric"><div class="label">{html.escape(label)}</div><div class="value">{html.escape(str(value))}</div></div>'


def render_agent_row(agent: object) -> str:
    if not isinstance(agent, dict):
        return ""
    status = str(agent.get("status", "unknown"))
    artifact_path = agent.get("artifact_path")
    artifact_link = link_artifact(artifact_path) if artifact_path else ""
    return (
        "<tr>"
        f"<td>{html.escape(str(agent.get('name', '')))}</td>"
        f'<td><span class="badge {html.escape(status)}">{html.escape(status)}</span></td>'
        f"<td>{html.escape(str(agent.get('started_at') or ''))}</td>"
        f"<td>{html.escape(str(agent.get('finished_at') or ''))}</td>"
        f"<td>{html.escape(str(agent.get('summary') or agent.get('error') or ''))}</td>"
        f"<td>{artifact_link}</td>"
        "</tr>"
    )


def render_agent_map(agents: dict[str, object]) -> str:
    grouped: dict[str, list[dict[str, object]]] = {}
    for agent in agents.values():
        if not isinstance(agent, dict):
            continue
        grouped.setdefault(str(agent.get("role", agent.get("name", "other"))), []).append(agent)
    groups = []
    for role, role_agents in grouped.items():
        nodes = []
        for agent in role_agents:
            status = html.escape(str(agent.get("status", "unknown")))
            stance = html.escape(str(agent.get("stance", "neutral")))
            nodes.append(
                f'<div class="agent-node {status}">'
                f'<div class="agent-name">{html.escape(str(agent.get("name", "")))}</div>'
                f'<span class="badge {status}">{status}</span> '
                f'<span class="label">{stance}</span>'
                f'<div>{html.escape(str(agent.get("summary") or agent.get("error") or ""))}</div>'
                "</div>"
            )
        groups.append(f'<section class="role-group"><div class="role-title">{html.escape(role)}</div>{"".join(nodes)}</section>')
    return "\n".join(groups)


def render_town_map(agents: dict[str, object]) -> str:
    grouped: dict[str, list[dict[str, object]]] = {}
    for agent in agents.values():
        if isinstance(agent, dict):
            grouped.setdefault(str(agent.get("role", agent.get("name", "other"))), []).append(agent)
    ordered_roles = ["main", "analyst", "supervisor", "researcher", "builder", "reviewer"]
    buildings = []
    for role in ordered_roles:
        role_agents = grouped.get(role, [])
        if not role_agents:
            continue
        avatars = "".join(render_town_avatar(agent) for agent in role_agents)
        buildings.append(
            f'<section class="building {html.escape(role)}">'
            f'<div class="building-title">{html.escape(role)}</div>'
            f'<div class="avatars">{avatars}</div>'
            "</section>"
        )
    return "\n".join(buildings)


def render_town_avatar(agent: dict[str, object]) -> str:
    name = str(agent.get("name", "agent"))
    status = html.escape(str(agent.get("status", "unknown")))
    stance = html.escape(str(agent.get("stance", "neutral")))
    initials = "".join(part[:1] for part in name.split("_")[:2]).upper()[:2] or "A"
    summary = html.escape(str(agent.get("summary") or agent.get("error") or ""))
    return (
        f'<div class="avatar {status}" title="{summary}">'
        f'<div class="head">{html.escape(initials)}</div>'
        f'<div class="agent-label">{html.escape(name)}</div>'
        f'<div class="stance">{stance}</div>'
        "</div>"
    )


def render_town_event(event: object) -> str:
    if not isinstance(event, dict):
        return ""
    return (
        '<div class="event">'
        f'<strong>{html.escape(str(event.get("event", "")))}</strong>'
        f'<span>{html.escape(str(event.get("at", "")))}</span>'
        "</div>"
    )


def render_event_row(event: object) -> str:
    if not isinstance(event, dict):
        return ""
    return (
        "<tr>"
        f"<td>{html.escape(str(event.get('at', '')))}</td>"
        f"<td>{html.escape(str(event.get('run_id', '')))}</td>"
        f"<td>{html.escape(str(event.get('event', '')))}</td>"
        f"<td>{html.escape(json.dumps(event.get('data', {}), ensure_ascii=True))}</td>"
        "</tr>"
    )


def render_artifact_row(artifact: object) -> str:
    if not isinstance(artifact, dict):
        return ""
    path = artifact.get("artifact_path")
    return (
        "<tr>"
        f"<td>{html.escape(str(artifact.get('agent', '')))}</td>"
        f"<td>{html.escape(str(artifact.get('summary', '')))}</td>"
        f"<td>{link_artifact(path) if path else ''}</td>"
        "</tr>"
    )


def link_artifact(path: object) -> str:
    label = html.escape(str(path))
    href = "/artifact?path=" + quote(str(path))
    return f'<a href="{href}">{label}</a>'


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    args = build_parser().parse_args()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = project_root / config_path
    serve_dashboard(project_root, config_path, args.host, args.port)


if __name__ == "__main__":
    main()
