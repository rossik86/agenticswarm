from __future__ import annotations

import json
import asyncio
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config.loader import read_prompt
from app.config.schema import AgentConfig, SwarmConfig
from app.tools.registry import build_tools


@dataclass
class AgentRunResult:
    text: str
    parsed_json: dict[str, Any] | None = None
    token_usage: dict[str, Any] | None = None


class AgentRunner:
    def __init__(self, project_root: Path, config: SwarmConfig) -> None:
        self.project_root = project_root
        self.config = config

    async def run(self, agent_name: str, input_text: str) -> AgentRunResult:
        agent_config = self.config.agents[agent_name]
        prompt = read_prompt(self.project_root, agent_config.prompt)
        provider = agent_config.provider or self.config.defaults.provider

        if provider == "codex_cli":
            return await self._run_codex_cli(agent_name, agent_config, prompt, input_text)
        if provider == "openhands":
            return await self._run_openhands(agent_name, agent_config, prompt, input_text)

        try:
            return await self._run_openai_agent(agent_name, agent_config, prompt, input_text)
        except ImportError as exc:
            raise RuntimeError(
                "Missing OpenAI Agents SDK. Install dependencies with `pip install -r requirements.txt`."
            ) from exc

    async def _run_openai_agent(
        self,
        agent_name: str,
        agent_config: AgentConfig,
        prompt: str,
        input_text: str,
    ) -> AgentRunResult:
        from agents import Agent, ModelSettings, Runner

        model = agent_config.model or self.config.defaults.model
        temperature = agent_config.temperature
        if temperature is None:
            temperature = self.config.defaults.temperature

        agent = Agent(
            name=agent_name,
            instructions=_compose_instructions(self.project_root, agent_config, prompt),
            model=model,
            model_settings=ModelSettings(temperature=temperature),
            tools=build_tools(agent_config.tools),
        )
        result = await Runner.run(agent, input_text)
        text = str(result.final_output)
        return AgentRunResult(text=text, parsed_json=_try_parse_json(text), token_usage=_openai_usage(result))

    async def _run_codex_cli(
        self,
        agent_name: str,
        agent_config: AgentConfig,
        prompt: str,
        input_text: str,
    ) -> AgentRunResult:
        cli_config = self.config.codex_cli
        full_prompt = "\n\n".join(
            [
                _compose_instructions(self.project_root, agent_config, prompt),
                "You are running as one specialist inside a parent multi-agent runtime.",
                "Return only the requested content. Do not ask interactive follow-up questions.",
                "Task input:",
                input_text,
            ]
        )

        command = _resolve_command(cli_config.command)
        args = [command, *cli_config.args]
        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(self.project_root),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(full_prompt.encode("utf-8")),
            timeout=cli_config.timeout_seconds,
        )

        output = stdout.decode("utf-8", errors="replace").strip()
        error_output = stderr.decode("utf-8", errors="replace").strip()
        if process.returncode != 0:
            raise RuntimeError(
                f"Codex CLI agent '{agent_name}' failed with exit code {process.returncode}: {error_output}"
            )

        text = output or error_output
        return AgentRunResult(text=text, parsed_json=_try_parse_json(text), token_usage=_codex_usage(output + "\n" + error_output))

    async def _run_openhands(
        self,
        agent_name: str,
        agent_config: AgentConfig,
        prompt: str,
        input_text: str,
    ) -> AgentRunResult:
        cli_config = self.config.openhands
        full_prompt = "\n\n".join(
            [
                _compose_instructions(self.project_root, agent_config, prompt),
                "You are running as the OpenHands-backed software agent inside a parent multi-agent runtime.",
                "Return concise implementation results or a clear failure reason.",
                "Task input:",
                input_text,
            ]
        )
        command = _resolve_command(cli_config.command)
        if command == cli_config.command and not shutil.which(command):
            raise RuntimeError(
                "OpenHands provider is configured but the `openhands` command is not available. "
                "Install OpenHands or set `openhands.command` in configs/agents.yaml."
            )
        args = [command, *cli_config.args]
        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(self.project_root),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(full_prompt.encode("utf-8")),
            timeout=cli_config.timeout_seconds,
        )
        output = stdout.decode("utf-8", errors="replace").strip()
        error_output = stderr.decode("utf-8", errors="replace").strip()
        if process.returncode != 0:
            raise RuntimeError(
                f"OpenHands agent '{agent_name}' failed with exit code {process.returncode}: {error_output}"
            )
        text = output or error_output
        return AgentRunResult(text=text, parsed_json=_try_parse_json(text))


def _try_parse_json(text: str) -> dict[str, Any] | None:
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


def _codex_usage(text: str) -> dict[str, Any] | None:
    match = re.search(r"tokens used\s+([0-9][0-9\s\u00a0,._]*)", text, flags=re.IGNORECASE)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(1))
    if not digits:
        return None
    return {"total_tokens": int(digits), "source": "codex_cli"}


def _openai_usage(result: Any) -> dict[str, Any] | None:
    usage = getattr(result, "usage", None)
    if usage is None:
        return None
    input_tokens = _usage_value(usage, "input_tokens", "prompt_tokens")
    output_tokens = _usage_value(usage, "output_tokens", "completion_tokens")
    total_tokens = _usage_value(usage, "total_tokens")
    if total_tokens is None and (input_tokens is not None or output_tokens is not None):
        total_tokens = (input_tokens or 0) + (output_tokens or 0)
    if total_tokens is None:
        return None
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "source": "agents_sdk",
    }


def _usage_value(usage: Any, *names: str) -> int | None:
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


def load_skill_markdowns(project_root: Path, skill_names: list[str]) -> list[dict[str, str]]:
    root = project_root.resolve()
    skill_root = (project_root / "skills").resolve()
    docs = []
    for skill_name in skill_names:
        path = (skill_root / f"{skill_name}.md").resolve()
        if root not in path.parents and path != root:
            continue
        if not path.exists() or not path.is_file():
            continue
        docs.append(
            {
                "name": skill_name,
                "path": str(path.relative_to(root)),
                "content": path.read_text(encoding="utf-8").strip(),
            }
        )
    return docs


def _compose_instructions(project_root: Path, agent_config: AgentConfig, prompt: str) -> str:
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


def _resolve_command(command: str) -> str:
    resolved = shutil.which(command)
    return resolved or command
