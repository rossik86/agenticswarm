from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from types import TracebackType
from typing import Any
from zoneinfo import ZoneInfo

from app.config.schema import ObservabilityConfig


class Observability:
    def __init__(self, project_root: Path, artifact_root: Path, config: ObservabilityConfig) -> None:
        self.project_root = project_root
        self.event_path = project_root / artifact_root / "events.jsonl"
        self.event_path.parent.mkdir(parents=True, exist_ok=True)
        self.config = config
        self.agentops = None
        if config.enabled and config.backend == "agentops":
            try:
                import agentops  # type: ignore
            except ImportError:
                self.emit("observability", "agentops_unavailable", {"message": "agentops is not installed"})
            else:
                self.agentops = agentops
                try:
                    agentops.init()
                except Exception as exc:  # pragma: no cover - depends on external service/config
                    self.emit("observability", "agentops_init_failed", {"error": str(exc)})

    def emit(self, run_id: str, event: str, data: dict[str, Any] | None = None) -> None:
        payload = {
            "at": _timestamp(),
            "run_id": run_id,
            "event": event,
            "data": data or {},
        }
        with self.event_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=True) + "\n")

    def span(self, run_id: str, name: str, data: dict[str, Any] | None = None) -> "Span":
        return Span(self, run_id, name, data or {})


@dataclass
class Span(AbstractContextManager["Span"]):
    observability: Observability
    run_id: str
    name: str
    data: dict[str, Any]

    def __enter__(self) -> "Span":
        self.started_at = datetime.now(ZoneInfo("Europe/Warsaw"))
        self.observability.emit(self.run_id, f"{self.name}.started", self.data)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        duration_ms = int((datetime.now(ZoneInfo("Europe/Warsaw")) - self.started_at).total_seconds() * 1000)
        data = {**self.data, "duration_ms": duration_ms}
        if exc:
            data["error"] = str(exc)
            self.observability.emit(self.run_id, f"{self.name}.failed", data)
        else:
            self.observability.emit(self.run_id, f"{self.name}.completed", data)
        return False


def _timestamp() -> str:
    return datetime.now(ZoneInfo("Europe/Warsaw")).isoformat(timespec="seconds")
