# Multiagent Swarm Architecture

## Design Inputs

The runtime follows these external design signals:

- LangGraph persistence/checkpointing: graph state should be saved after node execution so workflows can recover and resume.
- OpenAI Agents SDK: agents should be specialized, support handoffs/tools/guardrails, and produce traceable runs.
- OpenTelemetry GenAI conventions: agent/model/tool activity should be observable as spans/events with consistent names.

## Runtime Layers

```mermaid
flowchart TB
    User[User / GUI] --> Main[Main communicator]
    Main --> AnalystPanel[Analyst panel]
    AnalystPanel --> Supervisor[Supervisor task owner]
    Supervisor --> ResearchPanel[Research panel]
    ResearchPanel --> Builder[Builder]
    Builder --> ReviewPanel[Review panel]
    ReviewPanel --> Gate[Supervisor gate]
    Gate -->|accepted| MainFinal[Main final answer]
    Gate -->|needs revision| ResearchPanel

    MainFinal --> User

    AnalystPanel --> Artifacts[(Markdown artifacts)]
    ResearchPanel --> Artifacts
    Builder --> Artifacts
    ReviewPanel --> Artifacts

    Main --> Checkpoints[(SQLite checkpoints)]
    AnalystPanel --> Checkpoints
    Supervisor --> Checkpoints
    ResearchPanel --> Checkpoints
    Builder --> Checkpoints
    ReviewPanel --> Checkpoints
    Gate --> Checkpoints

    Main --> Events[(events.jsonl)]
    AnalystPanel --> Events
    Supervisor --> Events
    ResearchPanel --> Events
    Builder --> Events
    ReviewPanel --> Events
    Gate --> Events

    Events --> Dashboard[Dashboard / Agent map]
    Artifacts --> Dashboard
    Checkpoints --> Dashboard
```

## Role Model

```mermaid
flowchart LR
    subgraph MainRole[main]
      MainNeutral[main neutral]
    end

    subgraph SupervisorRole[supervisor]
      SupervisorNeutral[supervisor neutral]
    end

    subgraph AnalystRole[analyst]
      AnalystNeutral[neutral: practical spec]
      AnalystPositive[positive: what will work]
      AnalystNegative[negative: grill me]
    end

    subgraph ResearchRole[researcher]
      ResearchNeutral[neutral: focused research]
      ResearchNegative[negative: research critic]
    end

    subgraph BuilderRole[builder]
      BuilderNeutral[builder: single worker per task]
    end

    subgraph ReviewerRole[reviewer]
      ReviewerNeutral[neutral: review]
      ReviewerNegative[negative: quality/security]
      ReviewerPositive[positive: good principles]
    end

    MainNeutral --> AnalystRole
    AnalystRole --> SupervisorNeutral
    SupervisorNeutral --> ResearchRole
    ResearchRole --> BuilderNeutral
    BuilderNeutral --> ReviewerRole
    ReviewerRole --> SupervisorNeutral
```

## Backend And GUI Split

```mermaid
flowchart LR
    CLI[Backend CLI\npython -m app.cli] --> Graph[LangGraph role workflow]
    Graph --> Providers[Provider layer]
    Providers --> AgentsSDK[OpenAI Agents SDK]
    Providers --> CodexCLI[Codex CLI]
    Providers --> OpenHands[OpenHands provider]

    Graph --> SQLite[(memory.sqlite\ncheckpoints.sqlite)]
    Graph --> Runs[(workspace/runs)]
    Graph --> Events[(events.jsonl)]

    Dashboard[Dashboard HTTP\n127.0.0.1:8765] --> Runs
    Dashboard --> Events
    Dashboard --> SQLite
```

## Checkpoint Strategy

Each role node writes a checkpoint into `workspace/checkpoints.sqlite` after it returns state. The checkpoint stores:

- `run_id`
- graph node name
- JSON-safe state snapshot
- timestamp

This is intentionally separate from memory. Checkpoints are for recovery and replay. Memory is for future prompt context.

## Quality Gate

The reviewer panel returns neutral, negative/security, and positive quality opinions. The supervisor gate then checks:

- whether the plan was executed,
- whether tests or TDD/BDD evidence exists for code tasks,
- whether reviewer issues require another pass.

If quality or gate says `needs_revision`, the graph loops back to research/build until `max_review_retries` is reached.
