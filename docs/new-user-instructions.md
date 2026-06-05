# New User Instructions

This guide gets a new local user from clone to a configured multi-agent dashboard.

## 1. Install

```powershell
cd C:\codex\multiagent-swarm
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd frontend
npm install
npm run build
cd ..
```

## 2. Choose a Provider

The app supports:

- `agents_sdk` for OpenAI Agents SDK with `OPENAI_API_KEY`.
- `codex_cli` for local Codex CLI.
- `openhands` for a configured OpenHands command.
- `copilot` for a configured Copilot command or wrapper.

For OpenAI Agents SDK:

```powershell
$env:OPENAI_API_KEY="..."
```

For Codex CLI, confirm that this works:

```powershell
codex exec --skip-git-repo-check "cmd.exe /c ver"
```

For Copilot, configure `copilot.command` and `copilot.args` in `configs/agents.yaml`. The command should accept the prompt through stdin and return the result on stdout.

## 3. Start the Dashboard

```powershell
.\.venv\Scripts\python.exe -m app.cli --dashboard
```

Open:

```text
http://127.0.0.1:8765/town
```

## 4. Welcome Configuration

On first open, the Town UI shows a welcome configuration modal.

1. Select provider.
2. Select or type model.
3. Save.

The save action updates `configs/agents.yaml` in two places:

- `defaults.provider` and `defaults.model`
- every agent's `provider` and `model`

You can reopen this configuration later from the left drawer, tab `Start`.

## 5. Run the First Task

```powershell
.\.venv\Scripts\python.exe -m app.cli --provider codex_cli --prompt "Przygotuj plan aplikacji lotto"
```

Results are written to:

```text
workspace/runs/<run_id>/
```

The final user-facing artifact is usually:

```text
workspace/runs/<run_id>/final.md
```

## 6. What to Inspect in the GUI

- Town map: room status, active run flow, checkpoint progress.
- Right drawer: selected room or agent, current run IO, artifacts, checkpoints, timeline.
- Left drawer: agents, skills, MCP resources, templates, versions, run diff, and Start configuration.
- Top-right run picker: previous runs with filters by text, status, and date.

## 7. Verification

Run backend tests:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Run frontend tests and build:

```powershell
cd frontend
npm test
npm run build
```
