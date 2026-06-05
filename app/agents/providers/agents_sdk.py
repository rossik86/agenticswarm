from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agents.providers.base import AgentRunResult
from app.agents.providers.common import compose_instructions, try_parse_json, usage_value
from app.config.schema import AgentConfig, SwarmConfig
from app.tools.registry import build_tools


class OpenAIAgentsProvider:
    name = "agents_sdk"

    def __init__(self, project_root: Path, config: SwarmConfig) -> None:
        self.project_root = project_root
        self.config = config

    async def run(
        self,
        agent_name: str,
        agent_config: AgentConfig,
        prompt: str,
        input_text: str,
    ) -> AgentRunResult:
        try:
            from agents import Agent, ModelSettings, Runner
        except ImportError as exc:
            raise RuntimeError(
                "Missing OpenAI Agents SDK. Install dependencies with `pip install -r requirements.txt`."
            ) from exc

        model = agent_config.model or self.config.defaults.model
        temperature = agent_config.temperature
        if temperature is None:
            temperature = self.config.defaults.temperature
        agent = Agent(
            name=agent_name,
            instructions=compose_instructions(self.project_root, agent_config, prompt),
            model=model,
            model_settings=ModelSettings(temperature=temperature),
            tools=build_tools(agent_config.tools),
        )
        result = await Runner.run(agent, input_text)
        text = str(result.final_output)
        return AgentRunResult(
            text=text,
            parsed_json=try_parse_json(text),
            token_usage=parse_openai_usage(result),
            provider=self.name,
        )


def parse_openai_usage(result: Any) -> dict[str, Any] | None:
    usage = getattr(result, "usage", None)
    if usage is None:
        return None
    input_tokens = usage_value(usage, "input_tokens", "prompt_tokens")
    output_tokens = usage_value(usage, "output_tokens", "completion_tokens")
    total_tokens = usage_value(usage, "total_tokens")
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
