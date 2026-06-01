from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from app.agents.runner import AgentRunner, _codex_usage, _compose_instructions, load_skill_markdowns
from app.config.loader import load_config


def test_codex_cli_provider_uses_configured_subprocess() -> None:
    project_root = Path(__file__).resolve().parents[1]
    config = load_config(project_root / "configs" / "agents.yaml")
    config.agents["researcher"].provider = "codex_cli"
    config.codex_cli.command = sys.executable
    config.codex_cli.args = [
        "-c",
        "import json, sys; data=sys.stdin.read(); print(json.dumps({'ok': True, 'has_task': 'Task input:' in data}))",
    ]

    runner = AgentRunner(project_root, config)

    result = asyncio.run(runner.run("researcher", "check runner"))

    assert result.parsed_json == {"ok": True, "has_task": True}


def test_openhands_provider_uses_configured_subprocess() -> None:
    project_root = Path(__file__).resolve().parents[1]
    config = load_config(project_root / "configs" / "agents.yaml")
    config.agents["builder"].provider = "openhands"
    config.openhands.command = sys.executable
    config.openhands.args = [
        "-c",
        "import json, sys; data=sys.stdin.read(); print(json.dumps({'provider': 'openhands', 'has_task': 'Task input:' in data}))",
    ]

    runner = AgentRunner(project_root, config)

    result = asyncio.run(runner.run("builder", "check openhands"))

    assert result.parsed_json == {"provider": "openhands", "has_task": True}


def test_codex_usage_parser_handles_grouped_numbers() -> None:
    assert _codex_usage("tokens used\n10\u00a0248") == {"total_tokens": 10248, "source": "codex_cli"}


def test_agent_instructions_include_markdown_skill_files() -> None:
    project_root = Path(__file__).resolve().parents[1]
    config = load_config(project_root / "configs" / "agents.yaml")

    docs = load_skill_markdowns(project_root, config.agents["analyst_neutral"].skills)
    instructions = _compose_instructions(project_root, config.agents["analyst_neutral"], "Base prompt")

    assert any(doc["name"] == "analysis" for doc in docs)
    assert "Skill labels: analysis, clarification, specification" in instructions
    assert "Source: skills" in instructions
    assert "balanced analysis" in instructions
