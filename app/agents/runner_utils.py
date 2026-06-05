from __future__ import annotations

from pathlib import Path


def load_skill_markdowns(project_root: Path, skill_names: list[str]) -> list[dict[str, str]]:
    root = project_root.resolve()
    skill_root = (project_root / "skills").resolve()
    docs = []
    for skill_name in skill_names:
        path = (skill_root / f"{skill_name}.md").resolve()
        if root not in path.parents and path != root:
            continue
        if not path.exists() or not path.is_file():
            continue
        docs.append(
            {
                "name": skill_name,
                "path": str(path.relative_to(root)),
                "content": path.read_text(encoding="utf-8").strip(),
            }
        )
    return docs
