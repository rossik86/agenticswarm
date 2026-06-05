from __future__ import annotations

from app.dashboard.legacy import (
    apply_agent_preset,
    read_agent_presets,
    read_agent_settings,
    read_global_resources,
    read_mcp_resources,
    read_prompt_versions,
    read_run_diff,
    read_task_templates,
    record_resource_version,
    restore_resource_version,
    update_agent_runtime_settings,
    update_global_resource,
    update_mcp_resource,
    update_skill_resource,
    update_task_template,
)

__all__ = [
    "apply_agent_preset",
    "read_agent_presets",
    "read_agent_settings",
    "read_global_resources",
    "read_mcp_resources",
    "read_prompt_versions",
    "read_run_diff",
    "read_task_templates",
    "record_resource_version",
    "restore_resource_version",
    "update_agent_runtime_settings",
    "update_global_resource",
    "update_mcp_resource",
    "update_skill_resource",
    "update_task_template",
]
