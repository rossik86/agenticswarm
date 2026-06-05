from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path
from typing import Any

from app.agents.runner import AgentRunner
from app.dashboard.schemas import LearningProposal
from app.artifacts.manager import ArtifactManager
from app.checkpoint.store import CheckpointStore
from app.config.schema import SwarmConfig
from app.graph.state import AgentState
from app.memory.store import MemoryStore
from app.observability.manager import Observability
from app.runtime import RunStopped


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
        if state.get("accepted_async"):
            decision = state.get("main_decision") or {
                "delegate": True,
                "delegated_task": state["user_input"],
                "reason": "Accepted asynchronously and delegated to supervisor.",
            }
            self.artifacts.update_agent(run_id, "main", "completed", str(decision.get("reason", "Delegated.")))
            update = {"main_decision": decision}
            self.artifacts.record_room_io(run_id, "main", state["user_input"], decision, str(decision.get("reason", "Delegated.")))
            self._checkpoint(run_id, "main_async_acceptance", {**state, **update})
            return update
        self.artifacts.update_agent(run_id, "main", "running", "Deciding whether to delegate.")
        prompt = (
            "Decide whether this user request needs specialist work. If it does, pass the user's requested task to supervisor without changing intent. "
            "Return JSON: {\"delegate\": true|false, \"delegated_task\": \"...\", \"reason\": \"...\"}.\n\n"
            f"{_memory_block(state)}User request:\n{state['user_input']}"
        )
        result = await self._run_agent(run_id, "main", prompt, "agent.main_decision")
        decision = result.parsed_json or {
            "delegate": True,
            "delegated_task": state["user_input"],
            "reason": "Defaulting to supervised workflow.",
        }
        self.artifacts.update_agent(run_id, "main", "completed", decision.get("reason", "Decision complete."))
        update = {"main_decision": decision}
        self.artifacts.record_room_io(run_id, "main", state["user_input"], decision, str(decision.get("reason", "Decision complete.")))
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
                    "supervisor_plan": state.get("plan"),
                    "research": state.get("research_result"),
                    "memory_context": state.get("memory_context", ""),
                    "panel_role": agent_name,
                    "prior_council_outputs": panel_results,
                    "council_instruction": (
                        "Council order is positive first, negative second, neutral last. "
                        "If you are the neutral analyst, arbitrate the prior positive and negative positions. Only your agreed specification leaves this room."
                    ),
                },
                "Analysis panel",
            )
            panel_results.append({"agent": agent_name, "summary": metadata["summary"], "text": result.text[:2000]})
            artifacts.append(metadata)

        consensus_input = json.dumps(
            {
                "user_request": state["user_input"],
                "supervisor_plan": state.get("plan"),
                "research": state.get("research_result"),
                "analyst_outputs": panel_results,
                "instruction": "Create final agreed analysis/specification for builder. Return JSON with keys: questions, specification, risks, recommendation.",
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
        self.artifacts.record_room_io(
            run_id,
            "analyst",
            {"supervisor_plan": state.get("plan"), "research": state.get("research_result")},
            analysis,
            str(analysis.get("recommendation", "Analysis complete.")),
        )
        self._checkpoint(run_id, "analyst_panel", {**state, **update})
        return update

    async def supervisor_route(self, state: AgentState) -> AgentState:
        run_id = state["run_id"]
        self.artifacts.update_agent(run_id, "supervisor", "running", "Planning role workflow.")
        supervisor_input = json.dumps(
            {
                "task_from_main": (state.get("main_decision") or {}).get("delegated_task") or state["user_input"],
                "user_request": state["user_input"],
                "instruction": (
                    "Break the task into practical points if possible. Decide whether research is needed before analyst specification. "
                    "For domain tasks like lottery/lotto, request research into rules, context, and constraints. "
                    "Return JSON with keys: research_needed, research_tasks, preliminary_plan, analyst_task, builder_task."
                ),
            },
            ensure_ascii=True,
            indent=2,
        )
        result = await self._run_agent(run_id, "supervisor", _with_memory(state, supervisor_input), "agent.supervisor")
        plan = result.parsed_json or {
            "research_needed": True,
            "analysis_needed": True,
            "research_tasks": [{"title": "Research task", "instructions": state["user_input"]}],
            "preliminary_plan": [{"title": "Understand task", "instructions": state["user_input"]}],
            "analyst_task": {"title": "Analyze and specify", "instructions": state["user_input"]},
            "builder_task": {"title": "Build task", "instructions": state["user_input"]},
        }
        plan.setdefault("research_needed", _infer_research_needed(state["user_input"], plan))
        plan.setdefault("analysis_needed", _infer_analysis_needed(state["user_input"], plan))
        topology = build_execution_topology(plan)
        self.artifacts.record_execution_topology(run_id, topology)
        self.artifacts.update_agent(run_id, "supervisor", "completed", "Role workflow planned.")
        update = {"plan": plan, "execution_topology": topology, "selected_agents": topology.get("agents", [])}
        self.artifacts.record_room_io(run_id, "supervisor", supervisor_input, plan, "Initial supervisor plan ready.")
        self._checkpoint(run_id, "supervisor_route", {**state, **update})
        return update

    async def research_panel(self, state: AgentState) -> AgentState:
        run_id = state["run_id"]
        if not (state.get("plan") or {}).get("research_needed", True):
            update = {"research_result": {"skipped": True, "summary": "Supervisor skipped research.", "claims": []}, "claims": []}
            self.artifacts.record_claims(run_id, [])
            self.artifacts.record_room_io(run_id, "researcher", state.get("plan"), update["research_result"], "Research skipped.")
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
        claims = extract_grounding_claims(panel_results)
        research_result = {"panel": panel_results, "summary": "; ".join(item["summary"] for item in panel_results), "claims": claims}
        self.artifacts.record_claims(run_id, claims)
        update = {"research_result": research_result, "claims": claims, "artifacts": artifacts}
        self.artifacts.record_room_io(run_id, "researcher", state.get("plan"), research_result, research_result["summary"])
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
                "grounding_claims": state.get("claims") or (state.get("research_result") or {}).get("claims", []),
                "plan": state.get("plan"),
                "review_feedback": state.get("quality_result"),
                "instruction": (
                    "Produce the requested deliverable itself. Do not return a meta-plan, checklist, or implementation notes as the primary output. "
                    "For Markdown/specification/planning tasks, write the complete Markdown document body with substantive sections and concrete TDD/BDD cases when requested. "
                    "For learning-based refinement tasks, incorporate the learning recommendations into the finished artifact and include a short 'Co poprawiono wedlug learningu' section."
                    " Use only grounded domain claims from grounding_claims when making factual domain statements; if no claim exists, mark the fact as requiring verification."
                ),
            },
            "Builder",
        )
        artifacts = [*state.get("artifacts", []), metadata]
        build_result = {"summary": metadata["summary"], "artifact_path": metadata["artifact_path"], "text": result.text[:2000]}
        update = {
            "build_result": build_result,
            "artifacts": artifacts,
            "builder_attempts": state.get("builder_attempts", 0) + 1,
        }
        self.artifacts.record_room_io(
            state["run_id"],
            "builder",
            {"analysis": state.get("analysis"), "plan": state.get("plan"), "research": state.get("research_result")},
            build_result,
            metadata["summary"],
        )
        self._checkpoint(state["run_id"], "build_solution", {**state, **update})
        return update

    async def builder_completeness_gate(self, state: AgentState) -> AgentState:
        run_id = state["run_id"]
        build_result = state.get("build_result") or {}
        text = str(build_result.get("text") or "")
        artifact_path = build_result.get("artifact_path")
        if artifact_path:
            path = Path(str(artifact_path))
            if path.exists() and path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
        result = validate_builder_completeness(text, state["user_input"])
        update = {"builder_completeness": result}
        self.artifacts.record_room_io(run_id, "builder", build_result, result, str(result.get("summary", "")))
        self._checkpoint(run_id, "builder_completeness_gate", {**state, **update})
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
                    "grounding_claims": state.get("claims") or (state.get("research_result") or {}).get("claims", []),
                    "existing_artifacts": state.get("artifacts", []),
                    "stage_contract": (
                        "Review the current builder artifact as the candidate deliverable. "
                        "Do not fail because final.md does not exist yet; main writes final.md after supervisor gate. "
                        "Fail only for missing or incorrect substantive content, unsafe scope, untestable requirements, or quality/security issues."
                    ),
                    "prior_council_outputs": panel_results,
                    "council_instruction": (
                        "Council order is positive first, negative second, neutral reviewer last. "
                        "If you are the neutral reviewer, arbitrate prior reviews and make the final quality decision."
                    ),
                },
                "Review panel",
            )
            parsed = result.parsed_json or parse_review_output(result.text)
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
        self.artifacts.record_room_io(
            run_id,
            "reviewer",
            {"plan": state.get("plan"), "analysis": state.get("analysis"), "build": state.get("build_result")},
            quality_result,
            quality_result["summary"],
        )
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
                "instruction": (
                    "Check whether the substantive plan was executed in the builder/review artifacts. "
                    "Do not require final.md at this stage; main writes final.md after this gate. "
                    "For code tasks, confirm TDD/BDD or tests were run. For planning/specification tasks, confirm TDD/BDD scenarios are specified. "
                    "Return JSON: {status, issues, summary}."
                ),
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
        self.artifacts.record_room_io(run_id, "supervisor", gate_input, gate, str(gate.get("summary", "Supervisor gate complete.")))
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
                "learning": state.get("learning_result"),
                "grounding_claims": state.get("claims") or (state.get("research_result") or {}).get("claims", []),
                "artifacts": state.get("artifacts", []),
                "instruction": (
                    "Return only the final Markdown deliverable content. The system will save your response to final.md, so do not say that final.md is missing. "
                    "If the task is a plan/specification request, produce the complete plan/specification as the document body. "
                    "Use the builder artifact as the main candidate output and incorporate valid review/supervisor corrections. "
                    "Do not produce a process summary unless the user explicitly asked for a process report."
                ),
            },
            ensure_ascii=True,
            indent=2,
        )
        result = await self._run_agent(run_id, "main", _with_memory(state, final_input), "agent.final_response")
        final_artifact = self.artifacts.write_markdown(run_id, "main", "final.md", result.text)
        metadata = {
            "agent": "main",
            "status": "completed",
            "artifact_path": str(final_artifact.path),
            "summary": final_artifact.summary,
        }
        self.artifacts.add_artifact(run_id, metadata)
        self.artifacts.update_agent(run_id, "main", "completed", "Final answer ready.", artifact_path=str(final_artifact.path))
        update = {"final_answer": result.text, "artifacts": [*state.get("artifacts", []), metadata]}
        self.artifacts.record_room_io(run_id, "main", final_input, {"final_answer": result.text, "artifact": metadata}, "Final markdown ready.")
        self._checkpoint(run_id, "final_response", {**state, **update})
        return update

    async def self_learning(self, state: AgentState) -> AgentState:
        run_id = state["run_id"]
        payload = {
            "user_request": state["user_input"],
            "plan": state.get("plan"),
            "research": state.get("research_result"),
            "analysis": state.get("analysis"),
            "build": state.get("build_result"),
            "quality": state.get("quality_result"),
            "supervisor_gate": state.get("supervisor_gate"),
            "artifacts": state.get("artifacts", []),
            "instruction": (
                "Act as an evaluator-optimizer/reflection agent for the entire run. "
                "Assess every agent and room handoff for quality, missing context, hallucination risk, unclear contracts, and avoidable rework. "
                "Do not change the final deliverable directly; produce learning notes that main and future runs can use. "
                "Return Markdown with: run quality score, per-agent observations, flow issues, reusable lessons, prompt/skill/config recommendations, and next-run guardrails."
            ),
        }
        result, metadata = await self._run_artifact_agent(state, "self_learner", payload, "Self-learning quality pass")
        learning_result = {"summary": metadata["summary"], "artifact_path": metadata["artifact_path"], "text": result.text[:3000]}
        proposals = extract_learning_proposals(result.text)
        self.artifacts.record_learning_proposals(run_id, proposals)
        if self.memory:
            self.memory.remember(run_id, "self_learner", result.text[:1200])
        update = {"learning_result": learning_result, "learning_proposals": proposals, "artifacts": [*state.get("artifacts", []), metadata]}
        self.artifacts.record_room_io(
            run_id,
            "learner",
            payload,
            learning_result,
            metadata["summary"],
        )
        self._checkpoint(run_id, "self_learning", {**state, **update})
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
        if self.artifacts.stop_requested(run_id):
            raise RunStopped(f"Run {run_id} stopped before agent {agent_name}.")
        try:
            with self._span(run_id, span_name, {"agent": agent_name}):
                task = asyncio.create_task(self.runner.run(agent_name, input_text))
                while not task.done():
                    if self.artifacts.stop_requested(run_id):
                        task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await task
                        raise RunStopped(f"Run {run_id} stopped during agent {agent_name}.")
                    await asyncio.sleep(1)
                result = await task
                if result.token_usage:
                    self.artifacts.record_agent_usage(run_id, agent_name, result.token_usage)
                return result
        except RunStopped:
            self.artifacts.update_agent(run_id, agent_name, "stopped", "Run stopped by user.")
            raise
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
    return "supervisor" if decision.get("delegate", True) else "final"


def should_retry_review(state: AgentState, max_review_retries: int) -> str:
    quality = state.get("quality_result") or {}
    gate = state.get("supervisor_gate") or {}
    attempts = state.get("review_attempts", 0)
    if attempts <= max_review_retries and (
        quality.get("status") == "needs_revision" or gate.get("status") == "needs_revision"
    ):
        return "retry"
    return "final"


def should_run_research(state: AgentState) -> str:
    plan = state.get("plan") or {}
    if bool(plan.get("research_needed", True)):
        return "research"
    if bool(plan.get("analysis_needed", True)):
        return "analysis"
    return "build"


def should_run_analysis_after_research(state: AgentState) -> str:
    plan = state.get("plan") or {}
    return "analysis" if bool(plan.get("analysis_needed", True)) else "build"


def should_retry_builder_completeness(state: AgentState, max_attempts: int) -> str:
    completeness = state.get("builder_completeness") or {}
    attempts = state.get("builder_attempts", 0)
    if completeness.get("status") == "needs_revision" and attempts <= max_attempts:
        return "retry"
    return "review"


def build_execution_topology(plan: dict[str, Any]) -> dict[str, Any]:
    research_needed = bool(plan.get("research_needed", True))
    analysis_needed = bool(plan.get("analysis_needed", True))
    stages = ["main", "supervisor"]
    if research_needed:
        stages.append("researcher")
    if analysis_needed:
        stages.append("analyst")
    stages.extend(["builder", "reviewer", "learner", "main"])
    edges = [
        {"source": stages[index], "target": stages[index + 1], "status": "planned"}
        for index in range(len(stages) - 1)
    ]
    agents_by_role = {
        "main": ["main"],
        "supervisor": ["supervisor"],
        "researcher": RESEARCH_PANEL,
        "analyst": ANALYST_PANEL,
        "builder": ["builder"],
        "reviewer": REVIEW_PANEL,
        "learner": ["self_learner"],
    }
    agents = []
    for stage in stages:
        for agent in agents_by_role.get(stage, []):
            if agent not in agents:
                agents.append(agent)
    return {
        "mode": "dynamic",
        "research_needed": research_needed,
        "analysis_needed": analysis_needed,
        "stages": stages,
        "edges": edges,
        "agents": agents,
    }


def extract_grounding_claims(panel_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for item in panel_results:
        agent = str(item.get("agent") or "researcher")
        text = str(item.get("text") or "")
        for line in text.splitlines():
            stripped = line.strip(" -\t")
            if not stripped:
                continue
            lower = stripped.lower()
            has_url = "http://" in stripped or "https://" in stripped
            looks_like_claim = has_url or lower.startswith(("claim:", "fact:", "source:", "wniosek:", "fakt:"))
            if not looks_like_claim:
                continue
            claims.append(
                {
                    "id": f"CLM-{len(claims) + 1:03d}",
                    "claim": stripped[:600],
                    "source": _first_url(stripped),
                    "confidence": "medium" if has_url else "low",
                    "agent": agent,
                }
            )
            if len(claims) >= 40:
                return claims
    return claims


def extract_learning_proposals(text: str) -> list[dict[str, Any]]:
    parsed = _parse_json_object(text)
    if parsed and isinstance(parsed.get("proposals"), list):
        proposals: list[dict[str, Any]] = []
        for item in parsed["proposals"]:
            if not isinstance(item, dict):
                continue
            candidate = {
                "id": str(item.get("id") or f"LRN-{len(proposals) + 1:03d}"),
                "target": str(item.get("target") or "global"),
                "action": str(item.get("action") or "prompt_append"),
                "recommendation": str(item.get("recommendation") or item.get("reason") or ""),
                "reason": str(item.get("reason") or item.get("recommendation") or ""),
                "risk": str(item.get("risk") or "medium"),
                "requires_approval": bool(item.get("requires_approval", True)),
                "status": str(item.get("status") or "proposed"),
            }
            proposals.append(LearningProposal.model_validate(candidate).model_dump())
            if len(proposals) >= 12:
                break
        return proposals

    proposals: list[dict[str, Any]] = []
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith(("-", "*")):
            continue
        body = stripped.lstrip("-* ").strip()
        lower = body.lower()
        target = "global"
        if "builder" in lower:
            target = "builder"
        elif "reviewer" in lower or "review" in lower:
            target = "reviewer"
        elif "research" in lower:
            target = "researcher"
        elif "analyst" in lower:
            target = "analyst_neutral"
        action = "prompt_append" if "prompt" in lower or "instruction" in lower else "skill_add"
        proposals.append(
            LearningProposal.model_validate(
                {
                "id": f"LRN-{len(proposals) + 1:03d}",
                "target": target,
                "action": action,
                "recommendation": body[:500],
                "reason": body[:500],
                "risk": "medium",
                "requires_approval": True,
                "status": "proposed",
                }
            ).model_dump()
        )
        if len(proposals) >= 12:
            break
    return proposals


def _first_url(text: str) -> str | None:
    for part in text.split():
        if part.startswith(("http://", "https://")):
            return part.rstrip(").,;")
    return None


def _infer_research_needed(user_request: str, plan: dict[str, Any]) -> bool:
    text = f"{user_request} {json.dumps(plan, ensure_ascii=True)}".lower()
    return any(term in text for term in ["research", "źród", "zrod", "sprawd", "lotto", "prawo", "regulamin", "aktual"])


def _infer_analysis_needed(user_request: str, plan: dict[str, Any]) -> bool:
    text = f"{user_request} {json.dumps(plan, ensure_ascii=True)}".lower()
    if any(term in text for term in ["prosty", "quick", "tylko uruchom", "formatuj"]):
        return False
    return True


def validate_builder_completeness(text: str, user_request: str) -> dict[str, Any]:
    body = str(text or "").strip()
    request = str(user_request or "").lower()
    lower = body.lower()
    issues: list[str] = []
    wants_spec = any(term in request for term in ["spec", "specyfik", "markdown", "plan aplikacji", "tdd", "bdd"])
    wants_implementation = any(term in request for term in ["zrealizuj", "zakod", "codebase", "kod", "aplikacj", "implement"])
    meta_markers = ["build objective", "implementation steps", "files or components", "remaining risks", "verification result"]
    if any(marker in lower for marker in meta_markers):
        issues.append("builder output looks like a meta-plan instead of the requested deliverable")
    if wants_implementation:
        has_file_tree = any(marker in lower for marker in ["struktura plik", "file tree", "codebase", "src/", "app.", "package.json"])
        has_code_fence = "```" in body
        has_run_instruction = any(marker in lower for marker in ["uruchom", "run", "npm", "python", "start"])
        if not has_file_tree or not has_code_fence:
            issues.append("implementation request requires a concrete codebase with file structure and code blocks")
        if not has_run_instruction:
            issues.append("implementation request requires run instructions")
    if wants_spec:
        headings = body.count("\n## ") + (1 if body.startswith("## ") else 0)
        if len(body) < 4500:
            issues.append("spec/document artifact is too short to be complete")
        if headings < 5:
            issues.append("spec/document artifact has too few substantive sections")
        if "bdd" in request and "given" not in lower:
            issues.append("BDD scenarios are missing expected Given/When/Then content")
        if "tdd" in request and "expected" not in lower and "oczekiw" not in lower:
            issues.append("TDD cases are missing expected results")
    status = "needs_revision" if issues else "accepted"
    return {
        "status": status,
        "issues": issues,
        "summary": "Builder artifact accepted by completeness gate." if status == "accepted" else "; ".join(issues),
    }


def parse_review_output(text: str) -> dict[str, Any]:
    stripped = text.strip()
    parsed = _parse_json_object(stripped)
    if isinstance(parsed, dict):
        status = str(parsed.get("status") or "accepted")
        blocking = parsed.get("blocking_issues")
        issues = parsed.get("issues")
        return {
            **parsed,
            "status": "needs_revision" if status == "failed" else status,
            "blocking_issues": blocking if isinstance(blocking, list) else [],
            "quality_notes": parsed.get("quality_notes") if isinstance(parsed.get("quality_notes"), list) else [],
            "security_notes": parsed.get("security_notes") if isinstance(parsed.get("security_notes"), list) else [],
            "required_changes": parsed.get("required_changes") if isinstance(parsed.get("required_changes"), list) else [],
            "issues": issues if isinstance(issues, list) else [],
            "summary": str(parsed.get("summary") or parsed.get("reason") or text[:300]),
        }
    lower = stripped.lower()
    needs_revision = any(term in lower for term in ["needs_revision", "wymaga poprawy", "blocking", "blokuj"])
    return {
        "status": "needs_revision" if needs_revision else "accepted",
        "summary": text[:300],
        "issues": [],
        "blocking_issues": [],
        "quality_notes": [],
        "security_notes": [],
        "required_changes": [],
    }


def _parse_review_text(text: str) -> dict[str, Any]:
    return parse_review_output(text)


def _parse_json_object(text: str) -> dict[str, Any] | None:
    stripped = str(text or "").strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


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
