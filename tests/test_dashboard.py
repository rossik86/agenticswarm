from __future__ import annotations

from pathlib import Path
import sqlite3

from app.artifacts.manager import ArtifactManager
from app.dashboard import (
    append_checkpoint_action,
    append_town_action,
    apply_learning_actions,
    build_checkpoint_prompt,
    read_checkpoint,
    read_checkpoints,
    read_latest_status,
    read_recent_events,
    read_runs,
    read_status,
    read_agent_settings,
    read_global_resources,
    read_prompt_versions,
    restore_resource_version,
    read_run_diff,
    read_task_templates,
    render_dashboard,
    render_town,
    build_learning_improvement_prompt,
    read_onboarding,
    mark_latest_background_failure,
    prepare_learning_improvement,
    apply_welcome_configuration,
    update_task_template,
    update_agent_runtime_settings,
    update_global_resource,
)
from app.graph.nodes import validate_builder_completeness
from app.config.loader import load_config


def test_dashboard_reads_latest_status_and_renders_agents(tmp_path: Path) -> None:
    manager = ArtifactManager(tmp_path, Path("runs"))
    manager.start_run(
        "run-1",
        "Check status",
        ["main"],
        {"main": {"display_name": "Main Communications Officer", "skills": ["conversation"], "tools": [], "prompt_path": "prompts/main.md"}},
    )
    manager.record_agent_usage("run-1", "main", {"total_tokens": 1234, "source": "codex_cli"})
    manager.update_agent("run-1", "main", "completed", "Done")
    manager.finish_run("run-1", "completed", "Final")

    status = read_latest_status(tmp_path / "runs")
    event_path = tmp_path / "runs" / "events.jsonl"
    event_path.write_text('{"at":"now","run_id":"run-1","event":"agent.main.completed","data":{"duration_ms":1}}\n')
    events = read_recent_events(event_path)
    filtered_events = read_recent_events(event_path, run_id="run-1")
    html = render_dashboard(status, events)

    assert status["run_id"] == "run-1"
    assert status["path"].endswith("run-1")
    assert filtered_events[0]["run_id"] == "run-1"
    assert "Multiagent Swarm Dashboard" in html
    assert "main" in html
    assert "completed" in html
    assert "Final" in html
    assert "Recent Events" in html
    assert "agent.main.completed" in html
    assert status["token_usage"]["total_tokens"] == 1234
    assert status["token_usage"]["by_role"]["main"]["total_tokens"] == 1234
    assert status["agents"]["main"]["display_name"] == "Main Communications Officer"
    assert status["agents"]["main"]["skills"] == ["conversation"]


def test_town_view_renders_role_buildings(tmp_path: Path) -> None:
    manager = ArtifactManager(tmp_path, Path("runs"))
    manager.start_run("run-1", "Check town", ["main", "analyst_neutral", "builder", "reviewer_negative"])
    manager.update_agent("run-1", "analyst_neutral", "completed", "Done")

    status = read_latest_status(tmp_path / "runs")
    html = render_town(status, [{"at": "now", "run_id": "run-1", "event": "agent.analyst_neutral.completed"}])

    assert "Multiagent Swarm Town" in html
    assert "building analyst" in html
    assert "analyst_neutral" in html
    assert "Event Feed" in html


def test_checkpoint_api_helpers_read_and_log_actions(tmp_path: Path) -> None:
    db_path = tmp_path / "checkpoints.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            create table checkpoints (
                id integer primary key autoincrement,
                run_id text not null,
                node text not null,
                state_json text not null,
                created_at text not null
            )
            """
        )
        conn.execute(
            "insert into checkpoints(run_id, node, state_json, created_at) values (?, ?, ?, ?)",
            ("run-1", "analyst_panel", '{"analysis": {"summary": "ok"}}', "now"),
        )

    checkpoints = read_checkpoints(db_path, run_id="run-1")
    assert checkpoints[0]["node"] == "analyst_panel"
    assert "analysis" in checkpoints[0]["state_keys"]

    checkpoint = read_checkpoint(db_path, int(checkpoints[0]["id"]))
    assert checkpoint is not None
    assert checkpoint["run_id"] == "run-1"
    prompt = build_checkpoint_prompt("restart", checkpoint)
    assert "Uruchom od nowa etap review" in prompt
    assert "analyst_panel" in prompt

    action_path = tmp_path / "checkpoint_actions.jsonl"
    append_checkpoint_action(action_path, "resume", {"checkpoint_id": checkpoints[0]["id"]})
    assert '"action": "resume"' in action_path.read_text(encoding="utf-8")


def test_town_actions_persist_human_note_and_manual_handoff(tmp_path: Path) -> None:
    action_path = tmp_path / "town_actions.jsonl"

    note = append_town_action(action_path, "room_note", {"run_id": "run-1", "room": "analyst", "note": "Uwzględnij Lotto Plus"})
    handoff = append_town_action(action_path, "manual_handoff", {"run_id": "run-1", "source": "reviewer", "target": "builder", "reason": "Popraw artefakt"})

    body = action_path.read_text(encoding="utf-8")
    assert note["accepted"] is True
    assert handoff["accepted"] is True
    assert '"action": "room_note"' in body
    assert '"target": "builder"' in body


def test_dashboard_lists_runs_and_reads_artifact_only_run(tmp_path: Path) -> None:
    manager = ArtifactManager(tmp_path, Path("runs"))
    manager.start_run("run-1", "Input", ["main"])
    manager.finish_run("run-1", "completed", "Output")
    artifact_dir = tmp_path / "runs" / "manual-run"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "plan.md").write_text("# Plan\n", encoding="utf-8")

    runs = read_runs(tmp_path / "runs")
    run_ids = {run["run_id"] for run in runs}
    assert {"run-1", "manual-run"} <= run_ids

    manual = read_status(tmp_path / "runs", "manual-run")
    assert manual["status"] == "artifact_only"
    assert manual["artifacts"][0]["summary"] == "plan.md"


def test_dashboard_reads_agent_settings_from_config() -> None:
    project_root = Path(__file__).resolve().parents[1]
    config = load_config(project_root / "configs" / "agents.yaml")

    settings = read_agent_settings(project_root, config, "analyst_neutral")

    assert settings["display_name"] == "Neutral Analyst Arbiter"
    assert settings["effective_provider"] == "agents_sdk"
    assert settings["effective_model"] == "gpt-5.4-mini"
    assert "analysis" in settings["skills"]
    assert settings["skill_markdowns"][0]["path"] == "skills\\analysis.md" or settings["skill_markdowns"][0]["path"] == "skills/analysis.md"
    assert "balanced analysis" in settings["skill_markdowns"][0]["content"]
    assert "You are the neutral analyst" in settings["prompt"]


def test_dashboard_updates_agent_runtime_settings(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    config_path = tmp_path / "agents.yaml"
    config_path.write_text((project_root / "configs" / "agents.yaml").read_text(encoding="utf-8"), encoding="utf-8")

    result = update_agent_runtime_settings(
        config_path,
        {"agent": "builder", "provider": "codex_cli", "model": "gpt-5.3-codex", "temperature": "0.3"},
    )
    config = load_config(config_path)

    assert result["updated"] is True
    assert config.agents["builder"].provider == "codex_cli"
    assert config.agents["builder"].model == "gpt-5.3-codex"
    assert config.agents["builder"].temperature == 0.3


def test_welcome_configuration_applies_provider_and_model_to_all_agents(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    config_path = tmp_path / "configs" / "agents.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text((project_root / "configs" / "agents.yaml").read_text(encoding="utf-8"), encoding="utf-8")

    result = apply_welcome_configuration(
        tmp_path,
        config_path,
        {"provider": "copilot", "model": "gpt-5.4-mini"},
    )
    config = load_config(config_path)
    onboarding = read_onboarding(tmp_path, config)

    assert result["updated"] is True
    assert config.defaults.provider == "copilot"
    assert config.defaults.model == "gpt-5.4-mini"
    assert all(agent.provider == "copilot" for agent in config.agents.values())
    assert all(agent.model == "gpt-5.4-mini" for agent in config.agents.values())
    assert onboarding["configured"] is True
    assert onboarding["provider"] == "copilot"


def test_dashboard_global_skill_and_mcp_crud(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    config_path = tmp_path / "configs" / "agents.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text((project_root / "configs" / "agents.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "skills").mkdir()

    skill_result = update_global_resource(tmp_path, config_path, {"type": "skill", "name": "domain_guard", "content": "# Domain Guard"})
    mcp_result = update_global_resource(
        tmp_path,
        config_path,
        {"type": "mcp", "name": "browser_mcp", "command": "browser", "args": "--headless", "env": "A=B"},
    )
    config = load_config(config_path)
    resources = read_global_resources(tmp_path, config)

    assert skill_result["updated"] is True
    assert (tmp_path / "skills" / "domain_guard.md").exists()
    assert mcp_result["updated"] is True
    assert resources["mcp"][0]["name"] == "browser_mcp"
    assert resources["mcp"][0]["env"] == {"A": "B"}

    delete_result = update_global_resource(tmp_path, config_path, {"type": "skill", "action": "delete", "name": "domain_guard"})
    assert delete_result["updated"] is True
    assert not (tmp_path / "skills" / "domain_guard.md").exists()


def test_resource_version_restore_rolls_back_skill_content(tmp_path: Path) -> None:
    (tmp_path / "skills").mkdir()
    skill_path = tmp_path / "skills" / "quality.md"
    skill_path.write_text("# Old\n", encoding="utf-8")
    update_global_resource(tmp_path, tmp_path / "configs" / "agents.yaml", {"type": "skill", "name": "quality", "content": "# New"})
    version = read_prompt_versions(tmp_path)[0]

    result = restore_resource_version(tmp_path, str(version["id"]))

    assert result["updated"] is True
    assert skill_path.read_text(encoding="utf-8") == "# Old\n"


def test_learning_improvement_requires_learning_artifact(tmp_path: Path) -> None:
    manager = ArtifactManager(tmp_path, Path("runs"))
    manager.start_run("run-1", "Plan lotto", ["main", "self_learner"])
    manager.finish_run("run-1", "completed", "Final")

    result = prepare_learning_improvement(tmp_path, tmp_path / "runs", "run-1")

    assert result["accepted"] is False
    assert "learning.md" in result["message"]


def test_learning_improvement_prepares_artifact_without_new_run(tmp_path: Path) -> None:
    manager = ArtifactManager(tmp_path, Path("runs"))
    manager.start_run("run-1", "Plan lotto", ["main", "self_learner"])
    final = manager.write_markdown("run-1", "main", "final.md", "# Final\n")
    learning = manager.write_markdown("run-1", "self_learner", "learning.md", "**Next-Run Guardrails**\n- Improve builder.")
    manager.add_artifact("run-1", {"agent": "main", "artifact_path": str(final.path), "summary": final.summary})
    manager.add_artifact("run-1", {"agent": "self_learner", "artifact_path": str(learning.path), "summary": learning.summary})
    manager.finish_run("run-1", "completed", "Final")

    before_runs = {path.name for path in (tmp_path / "runs").iterdir() if path.is_dir()}
    result = prepare_learning_improvement(tmp_path, tmp_path / "runs", "run-1")
    after_runs = {path.name for path in (tmp_path / "runs").iterdir() if path.is_dir()}

    assert result["accepted"] is True
    assert "Nie uruchomiono nowego runu" in result["message"]
    assert before_runs == after_runs
    assert Path(str(result["artifact_path"])).exists()


def test_learning_improvement_prompt_is_compacted() -> None:
    status = {"run_id": "run-1", "user_input": "Plan lotto"}
    long_final = "# Final\n" + ("content\n" * 2000)
    long_learning = (
        "**Flow / Handoff Issues**\n"
        + ("Builder must output final markdown.\n" * 300)
        + "\n**Next-Run Guardrails**\n"
        + ("Reject outline-only artifacts.\n" * 300)
    )

    prompt = build_learning_improvement_prompt(status, long_learning, long_final)

    assert len(prompt) < 10000
    assert "skrócono długi kontekst" in prompt
    assert "Builder must output final markdown" in prompt


def test_background_failure_marks_latest_run_failed(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    config_path = tmp_path / "configs" / "agents.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text((project_root / "configs" / "agents.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    manager = ArtifactManager(tmp_path, Path("workspace/runs"))
    manager.start_run("run-1", "Prompt", ["main"])

    mark_latest_background_failure(tmp_path, config_path, "boom")
    status = read_latest_status(tmp_path / "workspace" / "runs")

    assert status["status"] == "failed"
    assert status["agents"]["main"]["status"] == "failed"
    assert status["errors"][0]["message"] == "boom"


def test_learning_actions_apply_selected_prompt_and_skill_changes(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    config_path = tmp_path / "configs" / "agents.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text((project_root / "configs" / "agents.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "prompts").mkdir()
    (tmp_path / "skills").mkdir()
    (tmp_path / "prompts" / "builder.md").write_text("Builder base\n", encoding="utf-8")

    result = apply_learning_actions(
        tmp_path,
        config_path,
        {
            "source_run_id": "run-1",
            "actions": [
                {"id": "a1", "type": "prompt_append", "target": "builder", "content": "Output final artifact only."},
                {"id": "a2", "type": "skill_create", "target": "artifact_completeness", "content": "# Artifact completeness"},
            ],
        },
    )

    assert result["updated"] is True
    assert "Output final artifact only." in (tmp_path / "prompts" / "builder.md").read_text(encoding="utf-8")
    assert (tmp_path / "skills" / "artifact_completeness.md").exists()


def test_builder_completeness_gate_rejects_meta_plan_and_accepts_spec() -> None:
    bad = validate_builder_completeness("Build Objective\n- implementation steps\n- remaining risks", "Przygotuj specyfikację markdown")
    full_sections = "\n\n".join(
        f"## Sekcja {index}\n" + ("Pełna treść specyfikacji z konkretnymi wymaganiami i kryteriami akceptacji. " * 12)
        for index in range(1, 8)
    )
    good = validate_builder_completeness(
        "# Specyfikacja\n\n"
        + full_sections
        + "\n\n## TDD\n- test: expected result dla walidacji.\n\n## BDD\nGiven user When opens Then sees content",
        "Przygotuj specyfikację markdown z TDD/BDD",
    )

    assert bad["status"] == "needs_revision"
    assert "meta-plan" in " ".join(bad["issues"])
    assert good["status"] == "accepted"


def test_run_diff_compares_scores_tokens_and_artifacts(tmp_path: Path) -> None:
    manager = ArtifactManager(tmp_path, Path("runs"))
    manager.start_run("run-a", "Input", ["main", "self_learner"])
    manager.record_agent_usage("run-a", "main", {"total_tokens": 10})
    learning_a = manager.write_markdown("run-a", "self_learner", "learning.md", "# Run Quality Score: 40/100")
    manager.add_artifact("run-a", {"agent": "self_learner", "artifact_path": str(learning_a.path), "summary": "score"})
    manager.finish_run("run-a", "completed", "A")
    manager.start_run("run-b", "Input", ["main", "self_learner"])
    manager.record_agent_usage("run-b", "main", {"total_tokens": 25})
    learning_b = manager.write_markdown("run-b", "self_learner", "learning.md", "# Run Quality Score: 70/100")
    manager.add_artifact("run-b", {"agent": "self_learner", "artifact_path": str(learning_b.path), "summary": "score"})
    manager.finish_run("run-b", "completed", "B")

    diff = read_run_diff(tmp_path / "runs", "run-a", "run-b")

    assert diff["score_delta"] == 30
    assert diff["token_delta"] == 15
    assert diff["runs"]["base"]["run_id"] == "run-a"
    assert diff["runs"]["target"]["run_id"] == "run-b"


def test_prompt_and_skill_updates_create_versions(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    config_path = tmp_path / "configs" / "agents.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text((project_root / "configs" / "agents.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "prompts").mkdir()
    (tmp_path / "skills").mkdir()
    (tmp_path / "prompts" / "builder.md").write_text("old prompt", encoding="utf-8")

    update_agent_runtime_settings(config_path, {"agent": "builder", "prompt": "new prompt"})
    update_global_resource(tmp_path, config_path, {"type": "skill", "name": "new_quality", "content": "# Quality"})
    versions = read_prompt_versions(tmp_path)

    assert any(item["resource"] == "prompts/builder.md" for item in versions)
    assert any(item["resource"] == "skills/new_quality.md" for item in versions)


def test_task_templates_crud(tmp_path: Path) -> None:
    initial = read_task_templates(tmp_path)
    result = update_task_template(
        tmp_path,
        {
            "id": "spec",
            "name": "Specyfikacja aplikacji",
            "prompt": "Przygotuj specyfikację",
            "required_artifacts": ["final.md", "learning.md"],
            "quality_gates": ["completeness"],
        },
    )
    templates = read_task_templates(tmp_path)

    assert initial["templates"]
    assert result["updated"] is True
    assert any(template["id"] == "spec" for template in templates["templates"])
