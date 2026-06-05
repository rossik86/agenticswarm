# Codebase Overview

## Backend

- `app/cli.py` - CLI entrypoint for interactive mode, one-shot prompts, and dashboard server.
- `app/main.py` - `SwarmApp`, runtime wiring, background run submission, memory, checkpoints, observability.
- `app/config/schema.py` - typed configuration schema for providers, agents, memory, checkpoints, and observability.
- `app/agents/runner.py` - provider execution layer for `agents_sdk`, `codex_cli`, `openhands`, and `copilot`.
- `app/graph/` - LangGraph orchestration and role handoff logic.
- `app/artifacts/manager.py` - run folders, markdown artifacts, status JSON, token usage aggregation.
- `app/checkpoint/store.py` - SQLite checkpoint persistence.
- `app/memory/store.py` - SQLite memory store.
- `app/dashboard.py` - HTTP dashboard API, static frontend serving, resource CRUD, onboarding config, learning actions.

## Frontend

- `frontend/src/main.jsx` - React Town dashboard, drawers, run picker, welcome configuration, agent/room inspectors.
- `frontend/src/styles.css` - full dashboard styling, town layout, drawers, modal, responsive behavior.
- `frontend/src/flowUtils.js` - run transition and React Flow step helpers.
- `frontend/src/runUtils.js` - run title, filtering, date, and sorting helpers.
- `frontend/src/dashboardInsights.js` - quality gates and scorecards.
- `frontend/src/townInteractions.js` - agent action labels, ambient state, room queue helpers.
- `frontend/src/assets/generated/` - generated pixel-art rooms and agents.

## Configuration

- `configs/agents.yaml` - provider defaults, provider commands, agent definitions, prompts, skills, tools, models.
- `prompts/*.md` - role prompts.
- `skills/*.md` - skill markdowns loaded into agent instructions.
- `workspace/onboarding.json` - local marker that welcome configuration has been completed.

## Runtime Data

- `workspace/runs/<run_id>/` - run status, final answer, per-agent artifacts.
- `workspace/runs/events.jsonl` - local observability event stream.
- `workspace/checkpoints.sqlite` - checkpoint snapshots.
- `workspace/memory.sqlite` - reusable run memory.
- `workspace/learning_improvements/` - generated improvement plans from the learner.

## Provider Contract

Each subprocess provider receives the composed prompt through stdin and should write the final answer to stdout.

- `codex_cli` defaults to `codex exec --skip-git-repo-check --color never -`.
- `openhands` is configured as a generic command wrapper.
- `copilot` is configured as a generic command wrapper, usually backed by GitHub CLI/Copilot or a local non-interactive script.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest
cd frontend
npm test
npm run build
```
