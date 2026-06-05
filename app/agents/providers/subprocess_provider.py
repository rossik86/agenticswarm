from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

from app.agents.providers.base import AgentRunResult
from app.agents.providers.common import compose_instructions, try_parse_json
from app.config.schema import AgentConfig, SwarmConfig


class SubprocessProvider:
    name = "subprocess"
    unavailable_message = "Provider command is not available."
    role_message = "You are running as a subprocess-backed agent inside a parent multi-agent runtime."

    def __init__(self, project_root: Path, config: SwarmConfig) -> None:
        self.project_root = project_root
        self.config = config

    def cli_config(self) -> Any:
        raise NotImplementedError

    async def run(
        self,
        agent_name: str,
        agent_config: AgentConfig,
        prompt: str,
        input_text: str,
    ) -> AgentRunResult:
        cli_config = self.cli_config()
        full_prompt = "\n\n".join(
            [
                compose_instructions(self.project_root, agent_config, prompt),
                self.role_message,
                "Return only the requested content. Do not ask interactive follow-up questions.",
                "Task input:",
                input_text,
            ]
        )
        command = shutil.which(cli_config.command) or cli_config.command
        if command == cli_config.command and not shutil.which(command):
            raise RuntimeError(self.unavailable_message)
        process = await asyncio.create_subprocess_exec(
            command,
            *cli_config.args,
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
            raise RuntimeError(f"{self.name} agent '{agent_name}' failed with exit code {process.returncode}: {error_output}")
        text = output or error_output
        return AgentRunResult(
            text=text,
            parsed_json=try_parse_json(text),
            token_usage={"source": self.name} if self.name == "copilot" else None,
            metadata={"command": command},
            provider=self.name,
        )
