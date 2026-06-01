from pathlib import Path

from app.artifacts.manager import ArtifactManager
from app.config.loader import load_config


def test_load_default_config() -> None:
    project_root = Path(__file__).resolve().parents[1]
    config = load_config(project_root / "configs" / "agents.yaml")

    assert "main" in config.agents
    assert "supervisor" in config.agents
    assert "analyst_negative" in config.agents
    assert "builder" in config.agents
    assert "reviewer_negative" in config.agents
    assert config.agents["researcher"].output_artifact == "researcher.md"


def test_artifact_run_id_uses_available_timezone(tmp_path: Path) -> None:
    manager = ArtifactManager(tmp_path, Path("runs"))

    run_id = manager.create_run_id()

    assert len(run_id) == len("20260531-123456-123456")
