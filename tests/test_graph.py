from __future__ import annotations

import asyncio
from pathlib import Path

from app.agents.runner import AgentRunResult
from app.artifacts.manager import ArtifactManager
from app.config.loader import load_config
from app.graph.builder import build_graph
from app.graph.nodes import (
    ANALYST_PANEL,
    RESEARCH_PANEL,
    REVIEW_PANEL,
    extract_grounding_claims,
    extract_learning_proposals,
    validate_builder_completeness,
)
from app.main import determine_final_run_status


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


class NoResearchRunner(FakeRunner):
    async def run(self, agent_name: str, input_text: str) -> AgentRunResult:
        if agent_name == "supervisor":
            self.calls.append((agent_name, input_text))
            return AgentRunResult(
                text='{"research_needed": false, "analysis_needed": false, "builder_task": {"title": "Build", "instructions": "Do it"}}',
                parsed_json={"research_needed": False, "analysis_needed": False, "builder_task": {"title": "Build", "instructions": "Do it"}},
            )
        return await super().run(agent_name, input_text)


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


def test_dynamic_topology_can_skip_research_and_analysis(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    config = load_config(project_root / "configs" / "agents.yaml")
    config.artifact_root = Path("runs")
    artifacts = ArtifactManager(tmp_path, config.artifact_root)
    artifacts.start_run("dynamic-run", "Simple format task", list(config.agents))
    runner = NoResearchRunner()
    graph = build_graph(project_root, config, runner, artifacts)
    initial_state = {
        "run_id": "dynamic-run",
        "user_input": "Simple format task",
        "memory_context": "",
        "messages": [{"role": "user", "content": "Simple format task"}],
        "artifacts": [],
        "specialist_results": [],
        "errors": [],
        "review_attempts": 0,
    }

    result = asyncio.run(graph.ainvoke(initial_state))
    calls = [agent for agent, _ in runner.calls]
    status = artifacts.read_status("dynamic-run")

    assert "researcher" not in calls
    assert "analyst_neutral" not in calls
    assert "builder" in calls
    assert result["execution_topology"]["stages"] == ["main", "supervisor", "builder", "reviewer", "learner", "main"]
    assert status["execution_topology"]["mode"] == "dynamic"


def test_council_order_uses_neutral_as_final_arbiter() -> None:
    assert ANALYST_PANEL == ["analyst_positive", "analyst_negative", "analyst_neutral"]
    assert RESEARCH_PANEL == ["researcher_negative", "researcher"]
    assert REVIEW_PANEL == ["reviewer_positive", "reviewer_negative", "reviewer"]


def test_grounding_claims_and_learning_proposals_are_structured() -> None:
    claims = extract_grounding_claims(
        [
            {
                "agent": "researcher",
                "text": "- Claim: Lotto uses official rules from https://example.com/rules",
            }
        ]
    )
    proposals = extract_learning_proposals("- Builder prompt should require source mapping.\n- Reviewer should enforce grounding.")

    assert claims[0]["id"] == "CLM-001"
    assert claims[0]["source"] == "https://example.com/rules"
    assert proposals[0]["target"] == "builder"
    assert proposals[0]["action"] == "prompt_append"


def test_builder_completeness_rejects_implementation_request_without_codebase() -> None:
    result = validate_builder_completeness(
        "## Plan\n\nZrobimy aplikację Lotto w kolejnych krokach.",
        "Przygotuj plan i zrealizuj aplikacje Lotto z instrukcja uruchomienia",
    )

    assert result["status"] == "needs_revision"
    assert any("codebase" in issue.lower() for issue in result["issues"])


def test_final_run_status_blocks_completed_when_revision_is_required() -> None:
    assert determine_final_run_status({"quality_result": {"status": "needs_revision"}}) == "needs_revision"
    assert determine_final_run_status({"supervisor_gate": {"status": "needs_revision"}}) == "needs_revision"
    assert determine_final_run_status({"learning_result": {"summary": "Quality decision: needs_revision"}}) == "needs_revision"
    assert determine_final_run_status({"quality_result": {"status": "accepted"}}) == "completed"


def test_final_run_status_accepts_complete_final_codebase_after_revision_feedback() -> None:
    final_answer = """
## Struktura plikow
```text
package.json
src/lotto.js
tests/lotto.test.js
```

## Codebase
### `package.json`
```json
{"scripts":{"test":"node --test"}}
```

### `src/lotto.js`
```js
export function generateLottoNumbers() { return [1, 2, 3, 4, 5, 6]; }
```

### `tests/lotto.test.js`
```js
import test from 'node:test';
```

## Uruchomienie
```bash
node --test
```
"""
    result = determine_final_run_status(
        {
            "user_input": "Przygotuj plan i zrealizuj aplikacje Lotto z instrukcja uruchomienia",
            "quality_result": {"status": "needs_revision"},
            "supervisor_gate": {"status": "needs_revision"},
            "final_answer": final_answer,
        }
    )

    assert result == "completed"


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
