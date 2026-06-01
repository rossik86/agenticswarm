from __future__ import annotations

from pathlib import Path
import sqlite3

from app.artifacts.manager import ArtifactManager
from app.dashboard import (
    append_checkpoint_action,
    build_checkpoint_prompt,
    read_checkpoint,
    read_checkpoints,
    read_latest_status,
    read_recent_events,
    read_runs,
    read_status,
    read_agent_settings,
    render_dashboard,
    render_town,
)
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
    assert "analysis" in settings["skills"]
    assert settings["skill_markdowns"][0]["path"] == "skills\\analysis.md" or settings["skill_markdowns"][0]["path"] == "skills/analysis.md"
    assert "balanced analysis" in settings["skill_markdowns"][0]["content"]
    assert "You are the neutral analyst" in settings["prompt"]
