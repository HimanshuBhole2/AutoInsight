# Rebuild Plan — Start Here

These docs are the plan for building the analytics agent again **from scratch, in a new repo**.
The current `AutoInsight` repo stays as it is. Use it only as a reference.

## Why restart?

The first version built the **infrastructure first** (Docker, CI/CD, Celery, Postgres, Alembic,
11 LangGraph nodes) before a single agent was proven to work. So when something broke, it was
hard to know *where*. That is why it felt confusing.

The new rule is simple:

> **Build one agent. Feed it input. Look at the output. Only move on when you trust it.**
> Infrastructure comes last, and only when you feel real pain without it.

## Read in this order

| # | File | What it tells you |
|---|------|-------------------|
| 1 | [01_architecture.md](01_architecture.md) | The big picture: what the system does, the agents, how data flows |
| 2 | [02_agents.md](02_agents.md) | Every agent: its job, exact input, exact output, how to test it alone |
| 3 | [03_tools.md](03_tools.md) | Which tools/libraries to use, why, and **in which phase** to add them |
| 4 | [04_roadmap.md](04_roadmap.md) | Step-by-step build order with "done" checkpoints |
| 5 | [05_io_testing.md](05_io_testing.md) | How to do input → output analysis for each agent |
| 6 | [06_repo_layout.md](06_repo_layout.md) | Folder structure for the new repo |
| — | [templates/](templates/) | Copy-paste templates: agent spec, I/O log, test fixtures |

## How to use this with the new repo

1. Create the new repo (any name you like — these docs call it `insight-agent`).
2. Copy this whole `planning/` folder into it as `docs/plan/`.
3. Follow [04_roadmap.md](04_roadmap.md) phase by phase. Tick the checkboxes as you go.
4. For every agent, fill an I/O log from [templates/agent_io_log.md](templates/agent_io_log.md).

## What to reuse from the old repo (copy ideas, not files)

| Old file | Worth reusing? | Note |
|---|---|---|
| `app/tools/sandbox.py` | **Yes, idea** | Env stripping + import allowlist + timeout is a good design. Rewrite it smaller. |
| `app/schemas/*.py` | **Yes, idea** | Pydantic contracts are right. New ones are simpler (see 02_agents.md). |
| `prompts/v1/*.txt` | Maybe | Read them for ideas; write new prompts while testing each agent. |
| `app/pipeline/graph.py` | No | The retry routing was tangled. New graph is built only after agents work. |
| Docker / CI / Celery / Alembic | Later | Phase 4–5. Do not touch at the start. |
