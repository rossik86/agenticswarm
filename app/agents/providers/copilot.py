from __future__ import annotations

from typing import Any

from app.agents.providers.subprocess_provider import SubprocessProvider


class CopilotProvider(SubprocessProvider):
    name = "copilot"
    role_message = "You are running as the Copilot-backed agent inside a parent multi-agent runtime."
    unavailable_message = (
        "Copilot provider is configured but its command is not available. "
        "Install GitHub CLI/Copilot or set `copilot.command` in configs/agents.yaml."
    )

    def cli_config(self) -> Any:
        return self.config.copilot
