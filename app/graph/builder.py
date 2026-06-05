from __future__ import annotations

from pathlib import Path

from langgraph.graph import END, START, StateGraph

from app.agents.runner import AgentRunner
from app.artifacts.manager import ArtifactManager
from app.config.schema import SwarmConfig
from app.graph.nodes import (
    SwarmNodes,
    should_delegate,
    should_run_analysis_after_research,
    should_run_research,
    should_retry_builder_completeness,
    should_retry_review,
)
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
    graph.add_node("builder_completeness_gate", nodes.builder_completeness_gate)
    graph.add_node("review_panel", nodes.review_panel)
    graph.add_node("supervisor_gate", nodes.supervisor_gate)
    graph.add_node("self_learning", nodes.self_learning)
    graph.add_node("final_response", nodes.final_response)

    graph.add_edge(START, "main_decision")
    graph.add_conditional_edges(
        "main_decision",
        should_delegate,
        {
            "supervisor": "supervisor_route",
            "final": "final_response",
        },
    )
    graph.add_conditional_edges(
        "supervisor_route",
        should_run_research,
        {
            "research": "research_panel",
            "analysis": "analyst_panel",
            "build": "build_solution",
        },
    )
    graph.add_conditional_edges(
        "research_panel",
        should_run_analysis_after_research,
        {
            "analysis": "analyst_panel",
            "build": "build_solution",
        },
    )
    graph.add_edge("analyst_panel", "build_solution")
    graph.add_edge("build_solution", "builder_completeness_gate")
    graph.add_conditional_edges(
        "builder_completeness_gate",
        lambda state: should_retry_builder_completeness(state, config.max_review_retries),
        {
            "retry": "build_solution",
            "review": "review_panel",
        },
    )
    graph.add_edge("review_panel", "supervisor_gate")
    graph.add_conditional_edges(
        "supervisor_gate",
        lambda state: should_retry_review(state, config.max_review_retries),
        {
            "retry": "analyst_panel",
            "final": "self_learning",
        },
    )
    graph.add_edge("self_learning", "final_response")
    graph.add_edge("final_response", END)

    return graph.compile()
