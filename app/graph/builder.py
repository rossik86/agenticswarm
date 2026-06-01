from __future__ import annotations

from pathlib import Path

from langgraph.graph import END, START, StateGraph

from app.agents.runner import AgentRunner
from app.artifacts.manager import ArtifactManager
from app.config.schema import SwarmConfig
from app.graph.nodes import SwarmNodes, should_delegate, should_retry_review
from app.graph.state import AgentState
from app.checkpoint.store import CheckpointStore
from app.memory.store import MemoryStore
from app.observability.manager import Observability


def build_graph(
    project_root: Path,
    config: SwarmConfig,
    runner: AgentRunner,
    artifacts: ArtifactManager,
    memory: MemoryStore | None = None,
    observability: Observability | None = None,
    checkpoints: CheckpointStore | None = None,
):
    nodes = SwarmNodes(
        project_root,
        config,
        runner,
        artifacts,
        memory=memory,
        observability=observability,
        checkpoints=checkpoints,
    )
    graph = StateGraph(AgentState)

    graph.add_node("main_decision", nodes.main_decision)
    graph.add_node("analyst_panel", nodes.analyst_panel)
    graph.add_node("supervisor_route", nodes.supervisor_route)
    graph.add_node("research_panel", nodes.research_panel)
    graph.add_node("build_solution", nodes.build_solution)
    graph.add_node("review_panel", nodes.review_panel)
    graph.add_node("supervisor_gate", nodes.supervisor_gate)
    graph.add_node("final_response", nodes.final_response)

    graph.add_edge(START, "main_decision")
    graph.add_conditional_edges(
        "main_decision",
        should_delegate,
        {
            "analyst": "analyst_panel",
            "final": "final_response",
        },
    )
    graph.add_edge("analyst_panel", "supervisor_route")
    graph.add_edge("supervisor_route", "research_panel")
    graph.add_edge("research_panel", "build_solution")
    graph.add_edge("build_solution", "review_panel")
    graph.add_edge("review_panel", "supervisor_gate")
    graph.add_conditional_edges(
        "supervisor_gate",
        lambda state: should_retry_review(state, config.max_review_retries),
        {
            "retry": "research_panel",
            "final": "final_response",
        },
    )
    graph.add_edge("final_response", END)

    return graph.compile()
