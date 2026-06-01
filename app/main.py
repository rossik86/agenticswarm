from __future__ import annotations

from pathlib import Path

from app.agents.factory import build_agent_runner
from app.artifacts.manager import ArtifactManager
from app.checkpoint.store import CheckpointStore
from app.config.loader import load_config
from app.graph.builder import build_graph
from app.graph.state import AgentState
from app.config.schema import ProviderType
from app.memory.store import MemoryStore
from app.observability.manager import Observability


class SwarmApp:
    def __init__(
        self,
        project_root: Path,
        config_path: Path,
        provider_override: ProviderType | None = None,
    ) -> None:
        self.project_root = project_root
        self.config = load_config(config_path)
        if provider_override:
            self.config.defaults.provider = provider_override
        self.artifacts = ArtifactManager(project_root, self.config.artifact_root)
        self.memory = None
        if self.config.memory.backend == "sqlite":
            self.memory = MemoryStore(project_root, self.config.memory.path, self.config.memory.max_context_items)
        self.checkpoints = CheckpointStore(project_root, self.config.checkpoint.path)
        self.observability = Observability(project_root, self.config.artifact_root, self.config.observability)
        self.runner = build_agent_runner(project_root, self.config)
        self.graph = build_graph(
            project_root,
            self.config,
            self.runner,
            self.artifacts,
            memory=self.memory,
            observability=self.observability,
            checkpoints=self.checkpoints,
        )

    async def run_turn(self, user_input: str) -> AgentState:
        run_id = self.artifacts.create_run_id()
        self.artifacts.start_run(run_id, user_input, list(self.config.agents))
        self.observability.emit(run_id, "run.started", {"user_input": user_input})
        memory_context = self.memory.context_for(user_input) if self.memory else ""
        initial_state: AgentState = {
            "run_id": run_id,
            "user_input": user_input,
            "memory_context": memory_context,
            "messages": [{"role": "user", "content": user_input}],
            "artifacts": [],
            "specialist_results": [],
            "errors": [],
            "review_attempts": 0,
        }
        try:
            result = await self.graph.ainvoke(initial_state)
        except Exception as exc:
            self.artifacts.finish_run(run_id, "failed", error=str(exc))
            self.observability.emit(run_id, "run.failed", {"error": str(exc)})
            raise

        self.artifacts.finish_run(run_id, "completed", final_answer=result.get("final_answer"))
        if self.memory and result.get("final_answer"):
            self.memory.remember(run_id, "main", str(result["final_answer"]))
        self.observability.emit(run_id, "run.completed", {"final_answer": result.get("final_answer")})
        return result
