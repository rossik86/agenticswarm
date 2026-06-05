from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TokenUsage(BaseModel):
    total_tokens: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    calls: int = 0
    sources: list[str] = Field(default_factory=list)
    by_agent: dict[str, Any] = Field(default_factory=dict)
    by_role: dict[str, Any] = Field(default_factory=dict)


class ArtifactSummary(BaseModel):
    agent: str = ""
    artifact_path: str | None = None
    summary: str = ""
    status: str | None = None


class AgentStatus(BaseModel):
    name: str = ""
    display_name: str = ""
    role: str = ""
    stance: str = ""
    status: str = "idle"
    summary: str = ""
    artifact_path: str | None = None
    error: str | None = None
    token_usage: TokenUsage = Field(default_factory=TokenUsage)


class RoomStatus(BaseModel):
    room: str = ""
    input: str = ""
    output: str = ""
    summary: str = ""
    history: list[dict[str, Any]] = Field(default_factory=list)


class CheckpointSummary(BaseModel):
    id: int | str | None = None
    run_id: str = ""
    node: str = ""
    created_at: str = ""
    state_keys: list[str] = Field(default_factory=list)


class LearningProposal(BaseModel):
    id: str = ""
    target: str = "global"
    action: str = "prompt_append"
    recommendation: str = ""
    reason: str = ""
    risk: str = "medium"
    requires_approval: bool = True
    status: str = "proposed"


class RunStatus(BaseModel):
    run_id: str = ""
    status: str = "unknown"
    user_input: str = ""
    started_at: str | None = None
    updated_at: str | None = None
    finished_at: str | None = None
    agents: dict[str, AgentStatus] = Field(default_factory=dict)
    artifacts: list[ArtifactSummary] = Field(default_factory=list)
    room_io: dict[str, RoomStatus] = Field(default_factory=dict)
    execution_topology: dict[str, Any] = Field(default_factory=dict)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    learning_proposals: list[LearningProposal] = Field(default_factory=list)
    roles: dict[str, list[str]] = Field(default_factory=dict)
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    final_answer: str | None = None
