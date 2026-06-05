from __future__ import annotations

import json
from pathlib import Path

from app.agents.providers.codex_cli import build_codex_args, parse_codex_usage
from app.dashboard import read_latest_status, render_town, serve_dashboard
from app.dashboard.schemas import LearningProposal, RunStatus
from app.graph.nodes import extract_learning_proposals, parse_review_output
from app.io.atomic import atomic_write_text


def test_dashboard_package_keeps_legacy_imports() -> None:
    assert callable(serve_dashboard)
    assert callable(read_latest_status)
    assert callable(render_town)


def test_provider_adapter_helpers_preserve_codex_behavior() -> None:
    assert build_codex_args("codex", ["exec", "--skip-git-repo-check", "-"], "gpt-5.4-mini") == [
        "exec",
        "--model",
        "gpt-5.4-mini",
        "--skip-git-repo-check",
        "-",
    ]
    assert parse_codex_usage("tokens used 12 345") == {"total_tokens": 12345, "source": "codex_cli"}


def test_atomic_write_text_replaces_content(tmp_path: Path) -> None:
    target = tmp_path / "config.yaml"
    target.write_text("old", encoding="utf-8")

    atomic_write_text(target, "new\n")

    assert target.read_text(encoding="utf-8") == "new\n"
    assert not list(tmp_path.glob("*.tmp"))


def test_status_schema_accepts_existing_shape() -> None:
    status = RunStatus.model_validate(
        {
            "run_id": "run-1",
            "status": "completed",
            "agents": {"main": {"name": "main", "status": "completed"}},
            "artifacts": [{"agent": "main", "artifact_path": "final.md", "summary": "Final"}],
            "token_usage": {"total_tokens": 10, "calls": 1, "by_agent": {}, "by_role": {}},
        }
    )

    assert status.run_id == "run-1"
    assert status.agents["main"].status == "completed"
    assert status.artifacts[0].summary == "Final"


def test_structured_review_and_learning_payloads_are_first_class() -> None:
    review = parse_review_output(
        json.dumps(
            {
                "status": "needs_revision",
                "blocking_issues": ["missing tests"],
                "quality_notes": ["add BDD"],
                "security_notes": [],
                "required_changes": ["write test matrix"],
            }
        )
    )
    proposals = extract_learning_proposals(
        json.dumps(
            {
                "proposals": [
                    {
                        "action": "prompt_append",
                        "target": "builder",
                        "reason": "Require richer acceptance criteria",
                        "risk": "low",
                        "requires_approval": True,
                    }
                ]
            }
        )
    )

    proposal = LearningProposal.model_validate(proposals[0])
    assert review["status"] == "needs_revision"
    assert review["blocking_issues"] == ["missing tests"]
    assert proposal.target == "builder"
    assert proposal.requires_approval is True
