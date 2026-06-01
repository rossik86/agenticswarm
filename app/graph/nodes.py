from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.agents.runner import AgentRunner
from app.artifacts.manager import ArtifactManager
from app.checkpoint.store import CheckpointStore
from app.config.schema import SwarmConfig
from app.graph.state import AgentState
from app.memory.store import MemoryStore
from app.observability.manager import Observability


ANALYST_PANEL = ["analyst_positive", "analyst_negative", "analyst_neutral"]
RESEARCH_PANEL = ["researcher_negative", "researcher"]
REVIEW_PANEL = ["reviewer_positive", "reviewer_negative", "reviewer"]


class SwarmNodes:
    def __init__(
        self,
        project_root: Path,
        config: SwarmConfig,
        runner: AgentRunner,
        artifacts: ArtifactManager,
        memory: MemoryStore | None = None,
        observability: Observability | None = None,
        checkpoints: CheckpointStore | None = None,
    ) -> None:
        self.project_root = project_root
        self.config = config
        self.runner = runner
        self.artifacts = artifacts
        self.memory = memory
        self.observability = observability
        self.checkpoints = checkpoints

    async def main_decision(self, state: AgentState) -> AgentState:
        run_id = state["run_id"]
        self.artifacts.update_agent(run_id, "main", "running", "Deciding whether to delegate.")
        prompt = (
            "Decide whether this user request needs specialist work. "
            "Return JSON: {\"delegate\": true|false, \"reason\": \"...\"}.\n\n"
            f"{_memory_block(state)}User request:\n{state['user_input']}"
        )
        result = await self._run_agent(run_id, "main", prompt, "agent.main_decision")
        decision = result.parsed_json or {"delegate": True, "reason": "Defaulting to supervised workflow."}
        self.artifacts.update_agent(run_id, "main", "completed", decision.get("reason", "Decision complete."))
        update = {"main_decision": decision}
        self._checkpoint(run_id, "main_decision", {**state, **update})
        return update

    async def analyst_panel(self, state: AgentState) -> AgentState:
        run_id = state["run_id"]
        artifacts = list(state.get("artifacts", []))
        panel_results = []
        for agent_name in ANALYST_PANEL:
            result, metadata = await self._run_artifact_agent(
                state,
                agent_name,
                {
                    "user_request": state["user_input"],
                    "memory_context": state.get("memory_context", ""),
                    "panel_role": agent_name,
                    "prior_council_outputs": panel_results,
                    "council_instruction": (
                        "Council order is positive first, negative second, neutral last. "
                        "If you are the neutral analyst, arbitrate the prior positive and negative positions and decide the final specification."
                    ),
                },
                "Analysis panel",
            )
            panel_results.append({"agent": agent_name, "summary": metadata["summary"], "text": result.text[:2000]})
            artifacts.append(metadata)

        consensus_input = json.dumps(
            {
                "user_request": state["user_input"],
                "analyst_outputs": panel_results,
                "instruction": "Create consensus analysis/specification. Return JSON with keys: questions, specification, risks, recommendation.",
            },
            ensure_ascii=True,
            indent=2,
        )
        result = await self._run_agent(run_id, "analyst_neutral", _with_memory(state, consensus_input), "agent.analysis_consensus")
        analysis = result.parsed_json or {
            "questions": [],
            "specification": result.text,
            "risks": [],
            "recommendation": "Proceed with supervised workflow.",
        }
        update = {"analysis": analysis, "artifacts": artifacts}
        self._checkpoint(run_id, "analyst_panel", {**state, **update})
        return update

    async def supervisor_route(self, state: AgentState) -> AgentState:
        run_id = state["run_id"]
        self.artifacts.update_agent(run_id, "supervisor", "running", "Planning role workflow.")
        supervisor_input = json.dumps(
            {
                "user_request": state["user_input"],
                "analysis": state.get("analysis"),
                "instruction": "Plan whether research is needed and define builder task. Return JSON with keys: research_needed, research_tasks, builder_task.",
            },
            ensure_ascii=True,
            indent=2,
        )
        result = await self._run_agent(run_id, "supervisor", _with_memory(state, supervisor_input), "agent.supervisor")
        plan = result.parsed_json or {
            "research_needed": True,
            "research_tasks": [{"title": "Research task", "instructions": state["user_input"]}],
            "builder_task": {"title": "Build task", "instructions": state["user_input"]},
        }
        self.artifacts.update_agent(run_id, "supervisor", "completed", "Role workflow planned.")
        update = {"plan": plan, "selected_agents": ["researcher", "builder", "reviewer"]}
        self._checkpoint(run_id, "supervisor_route", {**state, **update})
        return update

    async def research_panel(self, state: AgentState) -> AgentState:
        run_id = state["run_id"]
        if not (state.get("plan") or {}).get("research_needed", True):
            update = {"research_result": {"skipped": True, "summary": "Supervisor skipped research."}}
            self._checkpoint(run_id, "research_panel", {**state, **update})
            return update

        artifacts = list(state.get("artifacts", []))
        panel_results = []
        for agent_name in RESEARCH_PANEL:
            result, metadata = await self._run_artifact_agent(
                state,
                agent_name,
                {
                    "user_request": state["user_input"],
                    "analysis": state.get("analysis"),
                    "plan": state.get("plan"),
                    "panel_role": agent_name,
                    "prior_council_outputs": panel_results,
                    "council_instruction": (
                        "Council order is critic first, neutral researcher last. "
                        "If you are the neutral researcher, arbitrate the critique and decide the final research note."
                    ),
                },
                "Research panel",
            )
            panel_results.append({"agent": agent_name, "summary": metadata["summary"], "text": result.text[:2000]})
            artifacts.append(metadata)
        research_result = {"panel": panel_results, "summary": "; ".join(item["summary"] for item in panel_results)}
        update = {"research_result": research_result, "artifacts": artifacts}
        self._checkpoint(run_id, "research_panel", {**state, **update})
        return update

    async def build_solution(self, state: AgentState) -> AgentState:
        result, metadata = await self._run_artifact_agent(
            state,
            "builder",
            {
                "user_request": state["user_input"],
                "analysis": state.get("analysis"),
                "research": state.get("research_result"),
                "plan": state.get("plan"),
                "review_feedback": state.get("quality_result"),
                "instruction": "Build the requested solution or produce the exact implementation artifact. Include TDD/BDD verification for code tasks.",
            },
            "Builder",
        )
        artifacts = [*state.get("artifacts", []), metadata]
        build_result = {"summary": metadata["summary"], "artifact_path": metadata["artifact_path"], "text": result.text[:2000]}
        update = {"build_result": build_result, "artifacts": artifacts}
        self._checkpoint(state["run_id"], "build_solution", {**state, **update})
        return update

    async def review_panel(self, state: AgentState) -> AgentState:
        run_id = state["run_id"]
        artifacts = list(state.get("artifacts", []))
        panel_results = []
        for agent_name in REVIEW_PANEL:
            result, metadata = await self._run_artifact_agent(
                state,
                agent_name,
                {
                    "user_request": state["user_input"],
                    "analysis": state.get("analysis"),
                    "research": state.get("research_result"),
                    "build": state.get("build_result"),
                    "existing_artifacts": state.get("artifacts", []),
                    "prior_council_outputs": panel_results,
                    "council_instruction": (
                        "Council order is positive first, negative second, neutral reviewer last. "
                        "If you are the neutral reviewer, arbitrate prior reviews and make the final quality decision."
                    ),
                },
                "Review panel",
            )
            parsed = result.parsed_json or _parse_review_text(result.text)
            panel_results.append({"agent": agent_name, "review": parsed, "artifact": metadata})
            artifacts.append(metadata)

        needs_revision = any(item["review"].get("status") == "needs_revision" for item in panel_results)
        quality_result = {
            "status": "needs_revision" if needs_revision else "accepted",
            "panel": panel_results,
            "summary": _review_summary(panel_results),
        }
        update = {
            "quality_result": quality_result,
            "review_result": quality_result,
            "review_attempts": state.get("review_attempts", 0) + 1,
            "artifacts": artifacts,
        }
        self._checkpoint(run_id, "review_panel", {**state, **update})
        return update

    async def supervisor_gate(self, state: AgentState) -> AgentState:
        run_id = state["run_id"]
        self.artifacts.update_agent(run_id, "supervisor", "running", "Final gate: plan, TDD/BDD, and quality.")
        gate_input = json.dumps(
            {
                "user_request": state["user_input"],
                "plan": state.get("plan"),
                "analysis": state.get("analysis"),
                "research": state.get("research_result"),
                "build": state.get("build_result"),
                "quality": state.get("quality_result"),
                "instruction": "Check whether the plan was executed. For code tasks, confirm TDD/BDD or tests were run. Return JSON: {status, issues, summary}.",
            },
            ensure_ascii=True,
            indent=2,
        )
        result = await self._run_agent(run_id, "supervisor", _with_memory(state, gate_input), "agent.supervisor_gate")
        gate = result.parsed_json or {
            "status": "accepted",
            "issues": [],
            "summary": result.text,
        }
        self.artifacts.update_agent(run_id, "supervisor", "completed", gate.get("summary", "Supervisor gate complete."))
        update = {"supervisor_gate": gate}
        self._checkpoint(run_id, "supervisor_gate", {**state, **update})
        return update

    async def final_response(self, state: AgentState) -> AgentState:
        run_id = state["run_id"]
        self.artifacts.update_agent(run_id, "main", "running", "Synthesizing final answer.")
        final_input = json.dumps(
            {
                "user_request": state["user_input"],
                "analysis": state.get("analysis"),
                "plan": state.get("plan"),
                "research": state.get("research_result"),
                "build": state.get("build_result"),
                "quality": state.get("quality_result"),
                "supervisor_gate": state.get("supervisor_gate"),
                "artifacts": state.get("artifacts", []),
            },
            ensure_ascii=True,
            indent=2,
        )
        result = await self._run_agent(run_id, "main", _with_memory(state, final_input), "agent.final_response")
        self.artifacts.update_agent(run_id, "main", "completed", "Final answer ready.")
        update = {"final_answer": result.text}
        self._checkpoint(run_id, "final_response", {**state, **update})
        return update

    async def _run_artifact_agent(
        self,
        state: AgentState,
        agent_name: str,
        payload: dict[str, Any],
        stage: str,
    ):
        run_id = state["run_id"]
        agent_config = self.config.agents[agent_name]
        output_name = agent_config.output_artifact or f"{agent_name}.md"
        self.artifacts.update_agent(run_id, agent_name, "running", stage)
        result = await self._run_agent(
            run_id,
            agent_name,
            _with_memory(state, json.dumps(payload, ensure_ascii=True, indent=2)),
            f"agent.{agent_name}",
        )
        artifact = self.artifacts.write_markdown(run_id, agent_name, output_name, result.text)
        metadata = {
            "agent": agent_name,
            "status": "completed",
            "artifact_path": str(artifact.path),
            "summary": artifact.summary,
        }
        self.artifacts.update_agent(run_id, agent_name, "completed", artifact.summary, artifact_path=str(artifact.path))
        self.artifacts.add_artifact(run_id, metadata)
        if self.memory:
            self.memory.remember(run_id, agent_name, artifact.summary or result.text[:500])
        return result, metadata

    async def _run_agent(self, run_id: str, agent_name: str, input_text: str, span_name: str):
        try:
            with self._span(run_id, span_name, {"agent": agent_name}):
                result = await self.runner.run(agent_name, input_text)
                if result.token_usage:
                    self.artifacts.record_agent_usage(run_id, agent_name, result.token_usage)
                return result
        except Exception as exc:
            self.artifacts.update_agent(run_id, agent_name, "failed", error=str(exc))
            raise

    def _span(self, run_id: str, name: str, data: dict[str, Any]):
        if self.observability:
            return self.observability.span(run_id, name, data)
        return _NullSpan()

    def _checkpoint(self, run_id: str, node: str, state: dict[str, Any]) -> None:
        if self.checkpoints:
            self.checkpoints.save(run_id, node, state)
        if self.observability:
            self.observability.emit(run_id, "checkpoint.saved", {"node": node})


def should_delegate(state: AgentState) -> str:
    decision = state.get("main_decision") or {}
    return "analyst" if decision.get("delegate", True) else "final"


def should_retry_review(state: AgentState, max_review_retries: int) -> str:
    quality = state.get("quality_result") or {}
    gate = state.get("supervisor_gate") or {}
    attempts = state.get("review_attempts", 0)
    if attempts <= max_review_retries and (
        quality.get("status") == "needs_revision" or gate.get("status") == "needs_revision"
    ):
        return "retry"
    return "final"


def _parse_review_text(text: str) -> dict[str, Any]:
    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else {"status": "accepted", "summary": text[:300]}
    except json.JSONDecodeError:
        return {"status": "accepted", "summary": text[:300], "issues": []}


def _review_summary(panel_results: list[dict[str, Any]]) -> str:
    return " | ".join(str(item["review"].get("summary", ""))[:220] for item in panel_results)


class _NullSpan:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return False


def _memory_block(state: AgentState) -> str:
    memory_context = state.get("memory_context", "")
    return f"{memory_context}\n\n" if memory_context else ""


def _with_memory(state: AgentState, text: str) -> str:
    return _memory_block(state) + text
