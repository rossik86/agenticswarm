from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.config.schema import AgentConfig, SwarmConfig


@dataclass
class AgentRunResult:
    text: str
    parsed_json: dict[str, Any] | None = None
    token_usage: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    provider: str | None = None


class ProviderAdapter(Protocol):
    name: str

    def __init__(self, project_root: Path, config: SwarmConfig) -> None:
        ...

    async def run(
        self,
        agent_name: str,
        agent_config: AgentConfig,
        prompt: str,
        input_text: str,
    ) -> AgentRunResult:
        ...
