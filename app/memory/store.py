from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class MemoryRecord:
    run_id: str
    agent: str
    content: str
    created_at: str


class MemoryStore:
    def __init__(self, project_root: Path, path: Path, max_context_items: int = 8) -> None:
        self.path = project_root / path
        self.max_context_items = max_context_items
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def remember(self, run_id: str, agent: str, content: str) -> None:
        normalized = content.strip()
        if not normalized:
            return
        with self._connect() as conn:
            conn.execute(
                "insert into memories(run_id, agent, content, created_at) values (?, ?, ?, ?)",
                (run_id, agent, normalized, _timestamp()),
            )

    def search(self, query: str, agent: str | None = None, limit: int | None = None) -> list[MemoryRecord]:
        terms = [term.lower() for term in query.split() if len(term) > 2]
        limit = limit or self.max_context_items
        sql = "select run_id, agent, content, created_at from memories"
        params: list[object] = []
        clauses = []
        if agent:
            clauses.append("agent = ?")
            params.append(agent)
        if terms:
            clauses.append("(" + " or ".join("lower(content) like ?" for _ in terms) + ")")
            params.extend(f"%{term}%" for term in terms)
        if clauses:
            sql += " where " + " and ".join(clauses)
        sql += " order by id desc limit ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [MemoryRecord(*row) for row in rows]

    def context_for(self, query: str) -> str:
        records = self.search(query)
        if not records:
            return ""
        lines = ["Relevant memory:"]
        for record in records:
            lines.append(f"- [{record.agent} / {record.run_id}] {record.content[:500]}")
        return "\n".join(lines)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                create table if not exists memories (
                    id integer primary key autoincrement,
                    run_id text not null,
                    agent text not null,
                    content text not null,
                    created_at text not null
                )
                """
            )
            conn.execute("create index if not exists idx_memories_agent on memories(agent)")
            conn.execute("create index if not exists idx_memories_run_id on memories(run_id)")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)


def _timestamp() -> str:
    return datetime.now(ZoneInfo("Europe/Warsaw")).isoformat(timespec="seconds")
