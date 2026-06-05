from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.agents.factory import build_agent_runner
from app.artifacts.manager import ArtifactManager
from app.checkpoint.store import CheckpointStore
from app.config.loader import load_config
from app.graph.builder import build_graph
from app.graph.state import AgentState
from app.config.schema import ProviderType
from app.memory.store import MemoryStore
from app.observability.manager import Observability
from app.runtime import RunStopped


@dataclass(frozen=True)
class SubmittedRun:
    run_id: str
    message: str


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
        self._background_tasks: set[asyncio.Task[AgentState]] = set()
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
        run_id, initial_state = self._create_run(user_input)
        return await self._run_graph(run_id, initial_state)

    def submit_turn(self, user_input: str) -> SubmittedRun:
        run_id, initial_state = self._create_run(
            user_input,
            accepted_async=True,
            main_decision={"delegate": True, "reason": "Task accepted and delegated to supervisor."},
        )
        self.artifacts.update_agent(run_id, "main", "completed", "Task accepted and delegated to supervisor.")
        self.artifacts.update_agent(run_id, "supervisor", "running", "Task queued for supervised execution.")
        self.observability.emit(run_id, "run.accepted", {"user_input": user_input})
        task = asyncio.create_task(self._run_graph(run_id, initial_state))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return SubmittedRun(run_id=run_id, message="Zadanie przyjęte i przekazane do supervisora.")

    async def wait_for_background(self) -> None:
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

    def _create_run(
        self,
        user_input: str,
        accepted_async: bool = False,
        main_decision: dict[str, Any] | None = None,
    ) -> tuple[str, AgentState]:
        run_id = self.artifacts.create_run_id()
        self.artifacts.start_run(run_id, user_input, list(self.config.agents), self._agent_metadata())
        self.observability.emit(run_id, "run.started", {"user_input": user_input})
        memory_context = self.memory.context_for(user_input) if self.memory else ""
        initial_state: AgentState = {
            "run_id": run_id,
            "user_input": user_input,
            "accepted_async": accepted_async,
            "memory_context": memory_context,
            "main_decision": main_decision,
            "messages": [{"role": "user", "content": user_input}],
            "artifacts": [],
            "specialist_results": [],
            "errors": [],
            "review_attempts": 0,
        }
        return run_id, initial_state

    async def _run_graph(self, run_id: str, initial_state: AgentState) -> AgentState:
        try:
            result = await self.graph.ainvoke(initial_state)
        except RunStopped as exc:
            self.artifacts.finish_run(run_id, "stopped", error=str(exc))
            self.observability.emit(run_id, "run.stopped", {"reason": str(exc)})
            raise
        except Exception as exc:
            self.artifacts.finish_run(run_id, "failed", error=str(exc))
            self.observability.emit(run_id, "run.failed", {"error": str(exc)})
            raise

        final_status = determine_final_run_status(result)
        self.artifacts.finish_run(run_id, final_status, final_answer=result.get("final_answer"))
        if self.memory and result.get("final_answer"):
            self.memory.remember(run_id, "main", str(result["final_answer"]))
        self.observability.emit(run_id, f"run.{final_status}", {"final_answer": result.get("final_answer")})
        self.observability.emit(
            run_id,
            "main.notified",
            {
                "message": "Supervisor workflow completed and final answer is ready.",
                "artifact_count": len(result.get("artifacts", [])),
            },
        )
        return result

    def _agent_metadata(self) -> dict[str, dict[str, object]]:
        return {
            name: {
                "display_name": agent.display_name,
                "description": agent.description,
                "skills": agent.skills,
                "tools": agent.tools,
                "prompt_path": str(agent.prompt),
            }
            for name, agent in self.config.agents.items()
        }


def determine_final_run_status(result: AgentState) -> str:
    if _final_answer_satisfies_implementation_request(result):
        return "completed"
    for key in ("quality_result", "supervisor_gate", "review_result"):
        value = result.get(key)
        if isinstance(value, dict) and str(value.get("status") or "").lower() == "needs_revision":
            return "needs_revision"
    learning = result.get("learning_result")
    if isinstance(learning, dict):
        combined = " ".join(str(learning.get(key) or "") for key in ("summary", "text")).lower()
        if "needs_revision" in combined or "needs revision" in combined:
            return "needs_revision"
    return "completed"


def _final_answer_satisfies_implementation_request(result: AgentState) -> bool:
    request = str(result.get("user_input") or "").lower()
    if not any(term in request for term in ["zrealizuj", "zakod", "codebase", "kod", "aplikacj", "implement"]):
        return False
    final_answer = str(result.get("final_answer") or "")
    lower = final_answer.lower()
    has_codebase = any(marker in lower for marker in ["struktura plik", "file tree", "codebase", "src/", "package.json"])
    has_code_blocks = "```" in final_answer
    has_run_instructions = any(marker in lower for marker in ["uruchom", "node --test", "npm", "python", "start"])
    return has_codebase and has_code_blocks and has_run_instructions
