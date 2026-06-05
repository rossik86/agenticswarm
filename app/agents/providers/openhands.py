from __future__ import annotations

from typing import Any

from app.agents.providers.subprocess_provider import SubprocessProvider


class OpenHandsProvider(SubprocessProvider):
    name = "openhands"
    role_message = "You are running as the OpenHands-backed software agent inside a parent multi-agent runtime."
    unavailable_message = (
        "OpenHands provider is configured but the `openhands` command is not available. "
        "Install OpenHands or set `openhands.command` in configs/agents.yaml."
    )

    def cli_config(self) -> Any:
        return self.config.openhands
