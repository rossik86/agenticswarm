from __future__ import annotations

from pathlib import Path

from app.config.schema import ObservabilityConfig
from app.memory.store import MemoryStore
from app.observability.manager import Observability


def test_sqlite_memory_store_remembers_and_searches(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path, Path("memory.sqlite"))

    store.remember("run-1", "coder", "Use Codex CLI for coding tasks.")

    records = store.search("Codex coding")
    assert len(records) == 1
    assert records[0].agent == "coder"
    assert "Codex CLI" in records[0].content
    assert "Relevant memory" in store.context_for("coding")


def test_local_observability_writes_events(tmp_path: Path) -> None:
    obs = Observability(tmp_path, Path("runs"), ObservabilityConfig())

    with obs.span("run-1", "agent.test", {"agent": "tester"}):
        pass

    body = (tmp_path / "runs" / "events.jsonl").read_text(encoding="utf-8")
    assert "agent.test.started" in body
    assert "agent.test.completed" in body
