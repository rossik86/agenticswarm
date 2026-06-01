# Multiagent Swarm

CLI-first multi-agent runtime using LangGraph as the orchestration layer and OpenAI Agents SDK as the execution layer for individual LLM agents.

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

## Using Codex CLI Instead Of An API Key

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
  coder:
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
- provider: `agents_sdk` or `codex_cli`
- provider: `agents_sdk`, `codex_cli`, or `openhands`
- model
- temperature
- type
- tools
- delegation targets
- output artifact name

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

It renders roles as buildings and agents as status avatars grouped by role and stance.

## OpenHands Provider

OpenHands can be configured as a specialist backend, typically for the `coder` agent:

```yaml
agents:
  coder:
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
