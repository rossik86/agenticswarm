from __future__ import annotations

from typing import Any


def build_tools(tool_names: list[str]) -> list[Any]:
    if not tool_names:
        return []

    from agents import function_tool

    @function_tool
    def markdown_writer(title: str, body: str) -> str:
        """Format a Markdown artifact body with a title and content."""
        clean_title = title.strip().lstrip("#").strip()
        clean_body = body.strip()
        return f"# {clean_title}\n\n{clean_body}\n"

    registry = {
        "markdown_writer": markdown_writer,
    }

    unknown = [name for name in tool_names if name not in registry]
    if unknown:
        raise ValueError(f"Unknown tool(s) in agent config: {', '.join(unknown)}")

    return [registry[name] for name in tool_names]

