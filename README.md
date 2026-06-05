# Multiagent Swarm

CLI-first multi-agent runtime with a React dashboard for observing and steering a role-based AI agent swarm.

LangGraph is used as the orchestration layer. Agents can run through OpenAI Agents SDK, Codex CLI, OpenHands, or a configurable Copilot CLI wrapper.

## Features

- Role-based swarm: Main, Supervisor, Analyst Council, Research Council, Builder, Review Council, and Self-Learning Quality Optimizer.
- Council pattern: positive, negative, and neutral agents collaborate inside selected roles before a handoff leaves the room.
- Markdown artifacts per run and per agent under `workspace/runs/<run_id>/`.
- Checkpoints stored in SQLite for resume/restart workflows.
- Local memory store for concise context reuse between runs.
- Local observability with JSONL events, token usage, room IO, agent status, and run history.
- React Town dashboard at `/town` with pixel-art rooms, agents, run flow, progress checkpoints, drawers, and artifact inspection.
- Global configuration drawer for agents, skills, MCP resources, templates, versions, and run diffs.
- Welcome configuration GUI for new users: set provider and model once and apply them to all agents.
- Provider support: `agents_sdk`, `codex_cli`, `openhands`, and `copilot`.
- Provider health checks from the GUI before committing a provider/model setup.
- Agent presets for common work modes: coding, product planning, research, security review, and docs writer.
- `needs_revision` run status when review, supervisor gate, or learner feedback blocks clean completion.
- Dynamic execution topology: supervisor can skip research or analysis for simpler tasks and writes the per-run DAG to `execution_topology.json`.
- Knowledge grounding: researcher outputs are converted into structured claims in `claims.json` and passed to builder/reviewer.
- Evaluator-optimizer loop: self-learner produces structured proposals that can be approved from the GUI and applied to prompts/skills.

## Shape

```text
CLI User
  -> Main LLM Agent
  -> Supervisor LLM Agent
  -> Specialist LLM Agents
  -> Markdown Artifacts
  -> Reviewer LLM Agent
  -> Main LLM Agent
  -> CLI User
```

## Quick Start

```powershell
cd C:\codex\multiagent-swarm
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:OPENAI_API_KEY="..."
python -m app.cli
```

Run one task non-interactively:

```powershell
.\.venv\Scripts\python.exe -m app.cli --provider codex_cli --prompt "Przygotuj plan aplikacji lotto"
```

Run the dashboard:

```powershell
.\.venv\Scripts\python.exe -m app.cli --dashboard
```

Open:

```text
http://127.0.0.1:8765/town
```

For a new user, the Town UI opens a welcome configuration modal. Pick a provider and model, then save. The selection is written to `configs/agents.yaml` for `defaults` and every configured agent.

## Providers

Supported provider values:

- `agents_sdk` - OpenAI Agents SDK, uses `OPENAI_API_KEY`.
- `codex_cli` - local Codex CLI subprocess.
- `openhands` - configurable OpenHands subprocess.
- `copilot` - configurable Copilot subprocess, usually backed by GitHub CLI/Copilot or a local wrapper.

### Using Codex CLI Instead Of An API Key

You can run agents through the local Codex CLI by changing the provider in `configs/agents.yaml`.

For all agents:

```yaml
defaults:
  provider: codex_cli
```

Or at runtime:

```powershell
python -m app.cli --provider codex_cli --prompt "Prepare a short plan"
```

For one agent:

```yaml
agents:
  builder:
    provider: codex_cli
```

The default Codex command is:

```yaml
codex_cli:
  command: codex
  args:
    - exec
    - --skip-git-repo-check
    - --color
    - never
    - "-"
```

This assumes your installed Codex CLI supports `codex exec -` for non-interactive stdin prompts.

Update Codex CLI with one of the official install/update paths:

```powershell
codex --upgrade
```

or:

```powershell
npm install -g @openai/codex
```

## Configuration

Agents are configured in `configs/agents.yaml`. Each agent can define:

- base prompt file
- provider: `agents_sdk`, `codex_cli`, `openhands`, or `copilot`
- model
- temperature
- type
- tools
- delegation targets
- output artifact name

The fastest way to configure all agents is the welcome GUI:

1. Start the dashboard with `.\.venv\Scripts\python.exe -m app.cli --dashboard`.
2. Open `http://127.0.0.1:8765/town`.
3. Use the welcome modal or the left drawer tab `Start`.
4. Choose provider and model.
5. Save to apply the selection to every agent at once.

Use `Sprawdź provider` in the same screen to verify the selected provider before saving. Use the left drawer tab `Presets` to apply a role/model/skill setup for a specific kind of work.

Run artifacts can also include:

- `execution_topology.json` - planned dynamic route for the run.
- `claims.json` - grounded claims extracted from research.
- `learning_proposals.json` - self-learner proposals available for user approval.

## Artifacts

Each run creates a folder under `workspace/runs/<run_id>/`. Specialist and reviewer agents write Markdown files there and return metadata to their parent.

## Dashboard

Run the local dashboard:

```powershell
.\.venv\Scripts\python -m app.cli --dashboard
```

Open:

```text
http://127.0.0.1:8765
```

The dashboard refreshes every 5 seconds and shows the latest run, agent status, artifact links, final answer, and errors. The raw status is also available at:

```text
http://127.0.0.1:8765/status.json
```

The dashboard also shows an agent map and recent observability events. Raw events are available at:

```text
http://127.0.0.1:8765/events.json
```

AI Town-style role view:

```text
http://127.0.0.1:8765/town
```

It renders rooms around Main CO as an office/town map. React Flow overlays the run transitions between rooms, with checkpoint progress above the map.

## OpenHands Provider

OpenHands can be configured as a specialist backend, typically for the `builder` agent:

```yaml
agents:
  builder:
    provider: openhands
```

Configure the command in `configs/agents.yaml`:

```yaml
openhands:
  command: openhands
  args:
    - "--help"
  timeout_seconds: 1800
```

The default is a safe placeholder. Set `openhands.args` to the non-interactive command supported by your local OpenHands installation.

## Copilot Provider

The Copilot provider is a generic subprocess adapter. Configure it in `configs/agents.yaml`:

```yaml
copilot:
  command: gh
  args:
    - copilot
    - suggest
    - -t
    - shell
  timeout_seconds: 900
```

For reliable agent execution, prefer a non-interactive wrapper that accepts the prompt over stdin and writes the final answer to stdout. During tests you can point `copilot.command` to any executable and set `copilot.args` accordingly.

## Memory

The default memory backend is local SQLite:

```yaml
memory:
  backend: sqlite
  path: workspace/memory.sqlite
  max_context_items: 8
```

The app stores concise run outputs and injects relevant memories into future agent prompts.

## Observability

Local observability writes JSONL events to:

```text
workspace/runs/events.jsonl
```

AgentOps is supported as an optional backend:

```yaml
observability:
  backend: agentops
  enabled: true
```

Install and configure AgentOps separately before enabling it.

## More Docs

- [New user instructions](docs/new-user-instructions.md)
- [Codebase overview](docs/codebase.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Town layout guide](docs/town-layout-guide.md)
