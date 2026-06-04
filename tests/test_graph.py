from __future__ import annotations

import asyncio
from pathlib import Path

from app.agents.runner import AgentRunResult
from app.artifacts.manager import ArtifactManager
from app.config.loader import load_config
from app.graph.builder import build_graph
from app.graph.nodes import ANALYST_PANEL, RESEARCH_PANEL, REVIEW_PANEL


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def run(self, agent_name: str, input_text: str) -> AgentRunResult:
        self.calls.append((agent_name, input_text))
        if agent_name == "main" and "Decide whether" in input_text:
            return AgentRunResult(text='{"delegate": true}', parsed_json={"delegate": True})
        if agent_name == "supervisor":
            return AgentRunResult(
                text='{"research_needed": true, "research_tasks": [{"title": "Research", "instructions": "Analyze"}], "builder_task": {"title": "Build", "instructions": "Plan"}}',
                parsed_json={"research_needed": True, "research_tasks": [{"title": "Research"}], "builder_task": {"title": "Build"}},
            )
        if agent_name.startswith("reviewer"):
            return AgentRunResult(
                text='{"status": "accepted", "issues": [], "summary": "Looks good"}',
                parsed_json={"status": "accepted", "issues": [], "summary": "Looks good"},
            )
        if agent_name == "main":
            return AgentRunResult(text="Final answer", parsed_json=None)
        if agent_name == "self_learner":
            return AgentRunResult(text="# Learning\nImprove handoffs.", parsed_json=None)
        if agent_name == "analyst_neutral" and "consensus" in input_text.lower():
            return AgentRunResult(
                text='{"questions": [], "specification": "Spec", "risks": [], "recommendation": "Proceed"}',
                parsed_json={"questions": [], "specification": "Spec", "risks": [], "recommendation": "Proceed"},
            )
        return AgentRunResult(text=f"# {agent_name}\nDone.", parsed_json=None)


def test_graph_writes_specialist_and_review_artifacts(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    config = load_config(project_root / "configs" / "agents.yaml")
    config.artifact_root = Path("runs")
    artifacts = ArtifactManager(tmp_path, config.artifact_root)
    graph = build_graph(project_root, config, FakeRunner(), artifacts)
    initial_state = {
        "run_id": "test-run",
        "user_input": "Build a thing",
        "memory_context": "",
        "messages": [{"role": "user", "content": "Build a thing"}],
        "artifacts": [],
        "specialist_results": [],
        "errors": [],
        "review_attempts": 0,
    }

    result = asyncio.run(graph.ainvoke(initial_state))

    assert result["final_answer"] == "Final answer"
    assert {
        "analyst_neutral",
        "analyst_positive",
        "analyst_negative",
        "researcher",
        "researcher_negative",
        "builder",
        "reviewer",
        "reviewer_negative",
        "reviewer_positive",
        "self_learner",
    }.issubset({artifact["agent"] for artifact in result["artifacts"]})
    assert (tmp_path / "runs" / "test-run" / "researcher.md").exists()
    assert (tmp_path / "runs" / "test-run" / "builder.md").exists()
    assert (tmp_path / "runs" / "test-run" / "review.md").exists()
    assert (tmp_path / "runs" / "test-run" / "learning.md").exists()
    assert (tmp_path / "runs" / "test-run" / "final.md").exists()


def test_graph_routes_supervisor_before_analyst_and_records_room_io(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    config = load_config(project_root / "configs" / "agents.yaml")
    config.artifact_root = Path("runs")
    artifacts = ArtifactManager(tmp_path, config.artifact_root)
    artifacts.start_run("route-run", "Prepare lotto plan", list(config.agents))
    runner = FakeRunner()
    graph = build_graph(project_root, config, runner, artifacts)
    initial_state = {
        "run_id": "route-run",
        "user_input": "Prepare lotto plan",
        "memory_context": "",
        "messages": [{"role": "user", "content": "Prepare lotto plan"}],
        "artifacts": [],
        "specialist_results": [],
        "errors": [],
        "review_attempts": 0,
    }

    asyncio.run(graph.ainvoke(initial_state))
    calls = [agent for agent, _ in runner.calls]
    status = artifacts.read_status("route-run")

    assert calls.index("supervisor") < calls.index("analyst_positive")
    assert status["room_io"]["supervisor"]["history"]
    assert status["room_io"]["analyst"]["history"]
    assert status["room_io"]["learner"]["history"]
    assert status["agents"]["main"]["artifact_path"].endswith("final.md")
    assert calls.index("self_learner") < calls.index("main", calls.index("self_learner"))
    final_main_call = [text for agent, text in runner.calls if agent == "main"][-1]
    assert "system will save your response to final.md" in final_main_call


def test_council_order_uses_neutral_as_final_arbiter() -> None:
    assert ANALYST_PANEL == ["analyst_positive", "analyst_negative", "analyst_neutral"]
    assert RESEARCH_PANEL == ["researcher_negative", "researcher"]
    assert REVIEW_PANEL == ["reviewer_positive", "reviewer_negative", "reviewer"]


def test_async_acceptance_skips_blocking_main_decision(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    config = load_config(project_root / "configs" / "agents.yaml")
    config.artifact_root = Path("runs")
    artifacts = ArtifactManager(tmp_path, config.artifact_root)
    artifacts.start_run("async-run", "Build a thing", list(config.agents))
    runner = FakeRunner()
    graph = build_graph(project_root, config, runner, artifacts)
    initial_state = {
        "run_id": "async-run",
        "user_input": "Build a thing",
        "accepted_async": True,
        "main_decision": {"delegate": True, "reason": "Task accepted and delegated to supervisor."},
        "memory_context": "",
        "messages": [{"role": "user", "content": "Build a thing"}],
        "artifacts": [],
        "specialist_results": [],
        "errors": [],
        "review_attempts": 0,
    }

    result = asyncio.run(graph.ainvoke(initial_state))

    assert result["final_answer"] == "Final answer"
    assert not any(agent == "main" and "Decide whether" in text for agent, text in runner.calls)
