from __future__ import annotations

from pathlib import Path

from app.agents.runner import AgentRunner
from app.config.schema import SwarmConfig


def build_agent_runner(project_root: Path, config: SwarmConfig) -> AgentRunner:
    return AgentRunner(project_root=project_root, config=config)

