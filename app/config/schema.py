from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


AgentType = Literal["main", "supervisor", "specialist", "reviewer"]
ProviderType = Literal["agents_sdk", "codex_cli", "openhands"]
MemoryBackend = Literal["none", "sqlite", "mem0"]
ObservabilityBackend = Literal["local", "agentops"]


class LlmDefaults(BaseModel):
    provider: ProviderType = "agents_sdk"
    model: str = "gpt-4.1"
    temperature: float = 0.2


class CodexCliConfig(BaseModel):
    command: str = "codex"
    args: list[str] = Field(default_factory=lambda: ["exec", "--skip-git-repo-check", "-"])
    timeout_seconds: int = 900


class OpenHandsConfig(BaseModel):
    command: str = "openhands"
    args: list[str] = Field(default_factory=lambda: ["--help"])
    timeout_seconds: int = 1800


class MemoryConfig(BaseModel):
    backend: MemoryBackend = "sqlite"
    path: Path = Path("workspace/memory.sqlite")
    max_context_items: int = 8


class CheckpointConfig(BaseModel):
    path: Path = Path("workspace/checkpoints.sqlite")


class ObservabilityConfig(BaseModel):
    backend: ObservabilityBackend = "local"
    enabled: bool = True


class AgentConfig(BaseModel):
    type: AgentType
    provider: ProviderType | None = None
    display_name: str | None = None
    description: str = ""
    skills: list[str] = Field(default_factory=list)
    model: str | None = None
    temperature: float | None = None
    prompt: Path
    tools: list[str] = Field(default_factory=list)
    delegates_to: list[str] = Field(default_factory=list)
    output_artifact: str | None = None
    validates: list[str] = Field(default_factory=list)


class SwarmConfig(BaseModel):
    defaults: LlmDefaults = Field(default_factory=LlmDefaults)
    codex_cli: CodexCliConfig = Field(default_factory=CodexCliConfig)
    openhands: OpenHandsConfig = Field(default_factory=OpenHandsConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    checkpoint: CheckpointConfig = Field(default_factory=CheckpointConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    artifact_root: Path = Path("workspace/runs")
    max_review_retries: int = 1
    agents: dict[str, AgentConfig]
