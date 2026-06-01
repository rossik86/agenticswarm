from __future__ import annotations

from pathlib import Path

import yaml

from app.config.schema import SwarmConfig


def load_config(path: str | Path) -> SwarmConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file)
    return SwarmConfig.model_validate(raw)


def read_prompt(project_root: Path, prompt_path: Path) -> str:
    full_path = project_root / prompt_path
    return full_path.read_text(encoding="utf-8")

