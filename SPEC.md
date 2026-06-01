# Multiagent Swarm Specification

## Goal

Build a CLI-first multi-agent system where a main LLM agent interacts with the user, delegates work through a supervisor, receives Markdown work artifacts from specialist agents, and returns a reviewed final answer.

## Architecture

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

## Runtime Split

LangGraph owns orchestration:

- graph state
- node order
- conditional routing
- retry loop
- final aggregation

OpenAI Agents SDK owns single-agent execution:

- agent instructions
- model selection
- model settings
- tools
- future handoffs or guardrails

Codex CLI can also own single-agent execution when an agent or the default runtime sets:

```yaml
provider: codex_cli
```

In that mode the application sends the composed agent prompt to a local `codex exec` process. Authentication is handled by the Codex CLI installation, so the application does not require `OPENAI_API_KEY`.

## Config-Driven Agents

Agents are defined in `configs/agents.yaml`.

Each agent supports:

- `type`
- `provider`
- `description`
- `skills`
- `model`
- `temperature`
- `prompt`
- `tools`
- `delegates_to`
- `output_artifact`
- `validates`

## Artifact Contract

Each specialist produces a Markdown artifact in:

```text
workspace/runs/<run_id>/<agent-output-file>.md
```

Each completed specialist returns metadata:

```json
{
  "agent": "researcher",
  "status": "completed",
  "artifact_path": "workspace/runs/<run_id>/researcher.md",
  "summary": "short summary"
}
```

The reviewer also writes a Markdown artifact and returns a structured decision:

```json
{
  "status": "accepted",
  "issues": [],
  "summary": "short review summary",
  "review_artifact_path": "workspace/runs/<run_id>/review.md"
}
```

## MVP Flow

1. CLI reads user input.
2. Main agent decides whether to delegate.
3. Supervisor creates specialist tasks.
4. Runtime executes selected specialists.
5. Each specialist output is written to Markdown.
6. Reviewer evaluates the artifact set.
7. If review asks for revision, runtime retries up to `max_review_retries`.
8. Main agent synthesizes the final CLI response.

## Next Implementation Stages

1. Add real file-system editing tools for selected agents.
2. Add persistent memory and checkpoints.
3. Add richer tool permission policy per agent.
4. Add structured schemas for specialist outputs.
5. Add streaming CLI output.
6. Add trace logs with token and timing metadata.
