from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agents.providers import (
    AgentRunResult,
    CodexCliProvider,
    CopilotProvider,
    OpenAIAgentsProvider,
    OpenHandsProvider,
    ProviderAdapter,
)
from app.agents.providers.agents_sdk import parse_openai_usage
from app.agents.providers.codex_cli import build_codex_args, parse_codex_usage, resolve_command
from app.agents.providers.common import compose_instructions, try_parse_json, usage_value
from app.agents.runner_utils import load_skill_markdowns
from app.config.loader import read_prompt
from app.config.schema import AgentConfig, SwarmConfig


class AgentRunner:
    def __init__(self, project_root: Path, config: SwarmConfig) -> None:
        self.project_root = project_root
        self.config = config
        self._providers: dict[str, ProviderAdapter] = {
            "agents_sdk": OpenAIAgentsProvider(project_root, config),
            "codex_cli": CodexCliProvider(project_root, config),
            "openhands": OpenHandsProvider(project_root, config),
            "copilot": CopilotProvider(project_root, config),
        }

    async def run(self, agent_name: str, input_text: str) -> AgentRunResult:
        agent_config = self.config.agents[agent_name]
        prompt = read_prompt(self.project_root, agent_config.prompt)
        provider_name = agent_config.provider or self.config.defaults.provider
        provider = self._providers.get(provider_name) or self._providers["agents_sdk"]
        return await provider.run(agent_name, agent_config, prompt, input_text)

    async def _run_openai_agent(
        self,
        agent_name: str,
        agent_config: AgentConfig,
        prompt: str,
        input_text: str,
    ) -> AgentRunResult:
        return await self._providers["agents_sdk"].run(agent_name, agent_config, prompt, input_text)

    async def _run_codex_cli(
        self,
        agent_name: str,
        agent_config: AgentConfig,
        prompt: str,
        input_text: str,
    ) -> AgentRunResult:
        return await self._providers["codex_cli"].run(agent_name, agent_config, prompt, input_text)

    async def _run_openhands(
        self,
        agent_name: str,
        agent_config: AgentConfig,
        prompt: str,
        input_text: str,
    ) -> AgentRunResult:
        return await self._providers["openhands"].run(agent_name, agent_config, prompt, input_text)

    async def _run_copilot(
        self,
        agent_name: str,
        agent_config: AgentConfig,
        prompt: str,
        input_text: str,
    ) -> AgentRunResult:
        return await self._providers["copilot"].run(agent_name, agent_config, prompt, input_text)


def _try_parse_json(text: str) -> dict[str, Any] | None:
    return try_parse_json(text)


def _codex_usage(text: str) -> dict[str, Any] | None:
    return parse_codex_usage(text)


def _openai_usage(result: Any) -> dict[str, Any] | None:
    return parse_openai_usage(result)


def _usage_value(usage: Any, *names: str) -> int | None:
    return usage_value(usage, *names)


def _compose_instructions(project_root: Path, agent_config: AgentConfig, prompt: str) -> str:
    return compose_instructions(project_root, agent_config, prompt)


def _resolve_command(command: str) -> str:
    return resolve_command(command)


def _codex_args_with_model(command: str, args: list[str], model: str | None) -> list[str]:
    return build_codex_args(command, args, model)
