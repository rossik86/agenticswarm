from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo


class CheckpointStore:
    def __init__(self, project_root: Path, path: Path) -> None:
        self.path = project_root / path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def save(self, run_id: str, node: str, state: dict[str, Any]) -> None:
        payload = json.dumps(_json_safe(state), ensure_ascii=True)
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "insert into checkpoints(run_id, node, state_json, created_at) values (?, ?, ?, ?)",
                (run_id, node, payload, _timestamp()),
            )

    def latest(self, run_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.path) as conn:
            row = conn.execute(
                "select state_json from checkpoints where run_id = ? order by id desc limit 1",
                (run_id,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def _init_db(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                create table if not exists checkpoints (
                    id integer primary key autoincrement,
                    run_id text not null,
                    node text not null,
                    state_json text not null,
                    created_at text not null
                )
                """
            )
            conn.execute("create index if not exists idx_checkpoints_run on checkpoints(run_id)")


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(key): _json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [_json_safe(item) for item in value]
        return str(value)


def _timestamp() -> str:
    return datetime.now(ZoneInfo("Europe/Warsaw")).isoformat(timespec="seconds")
