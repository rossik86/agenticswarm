from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path

from app.agents.providers.base import AgentRunResult
from app.agents.providers.common import compose_instructions, try_parse_json
from app.config.schema import AgentConfig, SwarmConfig


class CodexCliProvider:
    name = "codex_cli"

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
        cli_config = self.config.codex_cli
        full_prompt = "\n\n".join(
            [
                compose_instructions(self.project_root, agent_config, prompt),
                "You are running as one specialist inside a parent multi-agent runtime.",
                "Return only the requested content. Do not ask interactive follow-up questions.",
                "Task input:",
                input_text,
            ]
        )
        command = resolve_command(cli_config.command)
        args = [command, *build_codex_args(command, cli_config.args, agent_config.model)]
        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(self.project_root),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(full_prompt.encode("utf-8")),
                timeout=cli_config.timeout_seconds,
            )
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise
        output = stdout.decode("utf-8", errors="replace").strip()
        error_output = stderr.decode("utf-8", errors="replace").strip()
        if process.returncode != 0:
            raise RuntimeError(
                f"Codex CLI agent '{agent_name}' failed with exit code {process.returncode}: {error_output}"
            )
        text = output or error_output
        return AgentRunResult(
            text=text,
            parsed_json=try_parse_json(text),
            token_usage=parse_codex_usage(output + "\n" + error_output),
            metadata={"command": command},
            provider=self.name,
        )


def resolve_command(command: str) -> str:
    resolved = shutil.which(command)
    return resolved or command


def build_codex_args(command: str, args: list[str], model: str | None) -> list[str]:
    if not model or Path(command).stem.lower() != "codex":
        return list(args)
    if "-m" in args or "--model" in args:
        return list(args)
    next_args = list(args)
    insert_at = 1 if next_args and next_args[0] == "exec" else 0
    next_args[insert_at:insert_at] = ["--model", model]
    return next_args


def parse_codex_usage(text: str) -> dict[str, int | str] | None:
    match = re.search(r"tokens used\s+([0-9][0-9\s\u00a0,._]*)", text, flags=re.IGNORECASE)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(1))
    if not digits:
        return None
    return {"total_tokens": int(digits), "source": "codex_cli"}
