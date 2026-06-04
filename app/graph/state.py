from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    run_id: str
    user_input: str
    accepted_async: bool
    memory_context: str
    messages: list[dict[str, Any]]
    main_decision: dict[str, Any] | None
    analysis: dict[str, Any] | None
    research_result: dict[str, Any] | None
    build_result: dict[str, Any] | None
    quality_result: dict[str, Any] | None
    supervisor_gate: dict[str, Any] | None
    learning_result: dict[str, Any] | None
    plan: dict[str, Any] | None
    selected_agents: list[str]
    tasks: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    specialist_results: list[dict[str, Any]]
    review_result: dict[str, Any] | None
    review_attempts: int
    final_answer: str | None
    errors: list[dict[str, Any]]
