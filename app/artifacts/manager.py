from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Artifact:
    agent: str
    path: Path
    summary: str


class ArtifactManager:
    def __init__(self, project_root: Path, artifact_root: Path) -> None:
        self.project_root = project_root
        self.artifact_root = project_root / artifact_root

    def create_run_id(self) -> str:
        now = datetime.now(ZoneInfo("Europe/Warsaw"))
        return now.strftime("%Y%m%d-%H%M%S-%f")

    def run_dir(self, run_id: str) -> Path:
        path = self.artifact_root / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def status_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "status.json"

    def latest_status_path(self) -> Path:
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        return self.artifact_root / "latest.json"

    def start_run(
        self,
        run_id: str,
        user_input: str,
        agent_names: list[str],
        agent_metadata: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        now = _timestamp()
        metadata = agent_metadata or {}
        status = {
            "run_id": run_id,
            "status": "running",
            "user_input": user_input,
            "started_at": now,
            "updated_at": now,
            "finished_at": None,
            "agents": {
                agent_name: {
                    "name": agent_name,
                    "display_name": metadata.get(agent_name, {}).get("display_name") or _agent_display_name(agent_name),
                    "description": metadata.get(agent_name, {}).get("description", ""),
                    "skills": metadata.get(agent_name, {}).get("skills", []),
                    "tools": metadata.get(agent_name, {}).get("tools", []),
                    "prompt_path": metadata.get(agent_name, {}).get("prompt_path"),
                    "role": _agent_role(agent_name),
                    "stance": _agent_stance(agent_name),
                    "status": "idle",
                    "started_at": None,
                    "finished_at": None,
                    "summary": "",
                    "artifact_path": None,
                    "error": None,
                    "token_usage": _empty_usage(),
                }
                for agent_name in agent_names
            },
            "artifacts": [],
            "room_io": {},
            "roles": _roles(agent_names),
            "token_usage": {
                "total_tokens": 0,
                "calls": 0,
                "by_agent": {},
                "by_role": {},
            },
            "errors": [],
            "final_answer": None,
        }
        self._write_status(run_id, status)

    def update_agent(
        self,
        run_id: str,
        agent_name: str,
        status: str,
        summary: str = "",
        artifact_path: str | None = None,
        error: str | None = None,
    ) -> None:
        data = self.read_status(run_id)
        now = _timestamp()
        agent = data.setdefault("agents", {}).setdefault(
            agent_name,
            {
                "name": agent_name,
                "display_name": _agent_display_name(agent_name),
                "description": "",
                "skills": [],
                "tools": [],
                "prompt_path": None,
                "role": _agent_role(agent_name),
                "stance": _agent_stance(agent_name),
                "status": "idle",
                "started_at": None,
                "finished_at": None,
                "summary": "",
                "artifact_path": None,
                "error": None,
                "token_usage": _empty_usage(),
            },
        )
        if status == "running" and not agent.get("started_at"):
            agent["started_at"] = now
        if status in {"completed", "failed"}:
            agent["finished_at"] = now
        agent["status"] = status
        if summary:
            agent["summary"] = summary
        if artifact_path:
            agent["artifact_path"] = artifact_path
        if error:
            agent["error"] = error
        data["updated_at"] = now
        self._write_status(run_id, data)

    def record_agent_usage(self, run_id: str, agent_name: str, token_usage: dict[str, Any]) -> None:
        total_tokens = _int_value(token_usage.get("total_tokens"))
        input_tokens = _int_value(token_usage.get("input_tokens"))
        output_tokens = _int_value(token_usage.get("output_tokens"))
        if total_tokens <= 0 and input_tokens <= 0 and output_tokens <= 0:
            return

        data = self.read_status(run_id)
        agent = data.setdefault("agents", {}).setdefault(
            agent_name,
            {
                "name": agent_name,
                "display_name": _agent_display_name(agent_name),
                "description": "",
                "skills": [],
                "tools": [],
                "prompt_path": None,
                "role": _agent_role(agent_name),
                "stance": _agent_stance(agent_name),
                "status": "idle",
                "started_at": None,
                "finished_at": None,
                "summary": "",
                "artifact_path": None,
                "error": None,
                "token_usage": _empty_usage(),
            },
        )
        usage = agent.setdefault("token_usage", _empty_usage())
        usage["total_tokens"] = _int_value(usage.get("total_tokens")) + total_tokens
        usage["input_tokens"] = _optional_sum(usage.get("input_tokens"), input_tokens)
        usage["output_tokens"] = _optional_sum(usage.get("output_tokens"), output_tokens)
        usage["calls"] = _int_value(usage.get("calls")) + 1
        sources = usage.setdefault("sources", [])
        source = token_usage.get("source")
        if source and source not in sources:
            sources.append(source)

        data["token_usage"] = _aggregate_usage(data.get("agents", {}))
        data["updated_at"] = _timestamp()
        self._write_status(run_id, data)

    def add_artifact(self, run_id: str, metadata: dict[str, Any]) -> None:
        data = self.read_status(run_id)
        artifacts = data.setdefault("artifacts", [])
        artifacts.append(metadata)
        data["updated_at"] = _timestamp()
        self._write_status(run_id, data)

    def record_room_io(self, run_id: str, room: str, input_data: Any, output_data: Any, summary: str = "") -> None:
        data = self.read_status(run_id)
        room_io = data.setdefault("room_io", {})
        record = {
            "room": room,
            "input": _compact_json(input_data),
            "output": _compact_json(output_data),
            "summary": summary,
            "updated_at": _timestamp(),
        }
        previous = room_io.get(room) if isinstance(room_io.get(room), dict) else {}
        history = list(previous.get("history", [])) if isinstance(previous, dict) and isinstance(previous.get("history"), list) else []
        history.append(record)
        room_io[room] = {**record, "history": history}
        data["updated_at"] = _timestamp()
        self._write_status(run_id, data)

    def finish_run(
        self,
        run_id: str,
        status: str,
        final_answer: str | None = None,
        error: str | None = None,
    ) -> None:
        data = self.read_status(run_id)
        now = _timestamp()
        data["status"] = status
        data["updated_at"] = now
        data["finished_at"] = now
        if status in {"completed", "failed", "stopped"}:
            for agent in data.get("agents", {}).values():
                if isinstance(agent, dict) and agent.get("status") == "running":
                    agent["status"] = status
                    agent["finished_at"] = now
        if final_answer:
            data["final_answer"] = final_answer
        if error:
            data.setdefault("errors", []).append({"message": error, "at": now})
        self._write_status(run_id, data)

    def read_status(self, run_id: str) -> dict[str, Any]:
        path = self.status_path(run_id)
        if not path.exists():
            return {
                "run_id": run_id,
                "status": "unknown",
                "agents": {},
                "artifacts": [],
                "errors": [],
            }
        return json.loads(path.read_text(encoding="utf-8"))

    def write_markdown(self, run_id: str, agent: str, filename: str, content: str) -> Artifact:
        path = self.run_dir(run_id) / filename
        body = content.strip() + "\n"
        path.write_text(body, encoding="utf-8")
        first_line = next((line.strip("# ").strip() for line in body.splitlines() if line.strip()), "")
        return Artifact(agent=agent, path=path, summary=first_line[:180])

    def _write_status(self, run_id: str, status: dict[str, Any]) -> None:
        body = json.dumps(status, ensure_ascii=True, indent=2)
        self.status_path(run_id).write_text(body + "\n", encoding="utf-8")
        self.latest_status_path().write_text(body + "\n", encoding="utf-8")


def _timestamp() -> str:
    return datetime.now(ZoneInfo("Europe/Warsaw")).isoformat(timespec="seconds")


def _agent_role(agent_name: str) -> str:
    if agent_name.startswith("analyst"):
        return "analyst"
    if agent_name.startswith("researcher"):
        return "researcher"
    if agent_name == "builder":
        return "builder"
    if agent_name.startswith("reviewer"):
        return "reviewer"
    return agent_name


def _agent_stance(agent_name: str) -> str:
    if agent_name.endswith("_positive"):
        return "positive"
    if agent_name.endswith("_negative"):
        return "negative"
    if agent_name.endswith("_neutral") or agent_name in {"main", "supervisor", "researcher", "builder", "reviewer"}:
        return "neutral"
    return "neutral"


def _agent_display_name(agent_name: str) -> str:
    names = {
        "main": "Main Communications Officer",
        "supervisor": "Task Supervisor",
        "analyst_positive": "Positive Analyst",
        "analyst_negative": "Negative Analyst",
        "analyst_neutral": "Neutral Analyst Arbiter",
        "researcher_negative": "Research Critic",
        "researcher": "Neutral Researcher Arbiter",
        "builder": "Builder",
        "reviewer_positive": "Positive Quality Reviewer",
        "reviewer_negative": "Quality and Security Guardian",
        "reviewer": "Neutral Review Arbiter",
    }
    return names.get(agent_name, agent_name.replace("_", " ").title())


def _roles(agent_names: list[str]) -> dict[str, list[str]]:
    roles: dict[str, list[str]] = {}
    for agent_name in agent_names:
        roles.setdefault(_agent_role(agent_name), []).append(agent_name)
    return roles


def _empty_usage() -> dict[str, Any]:
    return {
        "total_tokens": 0,
        "input_tokens": None,
        "output_tokens": None,
        "calls": 0,
        "sources": [],
    }


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _optional_sum(current: Any, addition: int) -> int | None:
    if addition <= 0 and current is None:
        return None
    return _int_value(current) + addition


def _aggregate_usage(agents: dict[str, Any]) -> dict[str, Any]:
    by_agent: dict[str, dict[str, Any]] = {}
    by_role: dict[str, dict[str, Any]] = {}
    total_tokens = 0
    calls = 0
    for agent_name, agent in agents.items():
        if not isinstance(agent, dict):
            continue
        usage = agent.get("token_usage")
        if not isinstance(usage, dict):
            continue
        agent_total = _int_value(usage.get("total_tokens"))
        agent_calls = _int_value(usage.get("calls"))
        if agent_total <= 0 and agent_calls <= 0:
            continue
        role = str(agent.get("role") or _agent_role(str(agent_name)))
        entry = {
            "total_tokens": agent_total,
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "calls": agent_calls,
        }
        by_agent[str(agent_name)] = entry
        role_entry = by_role.setdefault(role, {"total_tokens": 0, "input_tokens": None, "output_tokens": None, "calls": 0})
        role_entry["total_tokens"] += agent_total
        role_entry["input_tokens"] = _optional_sum(role_entry.get("input_tokens"), _int_value(usage.get("input_tokens")))
        role_entry["output_tokens"] = _optional_sum(role_entry.get("output_tokens"), _int_value(usage.get("output_tokens")))
        role_entry["calls"] += agent_calls
        total_tokens += agent_total
        calls += agent_calls
    return {"total_tokens": total_tokens, "calls": calls, "by_agent": by_agent, "by_role": by_role}


def _compact_json(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=True, indent=2)
