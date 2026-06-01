from __future__ import annotations

import asyncio
from pathlib import Path

from app.agents.runner import AgentRunResult
from app.artifacts.manager import ArtifactManager
from app.config.loader import load_config
from app.graph.builder import build_graph
from app.graph.nodes import ANALYST_PANEL, RESEARCH_PANEL, REVIEW_PANEL


class FakeRunner:
    async def run(self, agent_name: str, input_text: str) -> AgentRunResult:
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
    }.issubset({artifact["agent"] for artifact in result["artifacts"]})
    assert (tmp_path / "runs" / "test-run" / "researcher.md").exists()
    assert (tmp_path / "runs" / "test-run" / "builder.md").exists()
    assert (tmp_path / "runs" / "test-run" / "review.md").exists()


def test_council_order_uses_neutral_as_final_arbiter() -> None:
    assert ANALYST_PANEL == ["analyst_positive", "analyst_negative", "analyst_neutral"]
    assert RESEARCH_PANEL == ["researcher_negative", "researcher"]
    assert REVIEW_PANEL == ["reviewer_positive", "reviewer_negative", "reviewer"]
