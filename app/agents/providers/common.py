from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.agents.runner_utils import load_skill_markdowns
from app.config.schema import AgentConfig


def try_parse_json(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def compose_instructions(project_root: Path, agent_config: AgentConfig, prompt: str) -> str:
    parts = []
    if agent_config.description:
        parts.append(f"Agent description: {agent_config.description}")
    if agent_config.skills:
        parts.append("Skill labels: " + ", ".join(agent_config.skills))
    skill_docs = load_skill_markdowns(project_root, agent_config.skills)
    if skill_docs:
        rendered_docs = "\n\n".join(
            f"## {doc['name']}\nSource: {doc['path']}\n\n{doc['content']}" for doc in skill_docs
        )
        parts.append("Skill markdowns loaded for this agent:\n\n" + rendered_docs)
    parts.append(prompt)
    return "\n\n".join(parts)


def usage_value(usage: Any, *names: str) -> int | None:
    for name in names:
        value = getattr(usage, name, None)
        if value is None and isinstance(usage, dict):
            value = usage.get(name)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None
