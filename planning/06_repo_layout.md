# 06 — New Repo Layout

Grow into this layout. Folders marked *(later)* don't exist until that phase.

```
insight-agent/
├── README.md
├── pyproject.toml
├── .env.example                 # LLM_API_KEY=...
├── .gitignore                   # .env, runs/, .venv/
├── docs/
│   └── plan/                    # ← copy of these planning docs
│
├── src/insight_agent/
│   ├── schemas.py               # ALL Pydantic models (one file at first)
│   ├── config.py                # settings: model names, budgets, timeouts
│   │
│   ├── agents/                  # one file per agent, each runnable alone
│   │   ├── profiler.py          #   def run(inp: ProfilerIn) -> DataProfile
│   │   ├── goal_parser.py
│   │   ├── planner.py
│   │   ├── code_writer.py
│   │   ├── executor.py
│   │   ├── checker.py
│   │   ├── narrator.py
│   │   └── assembler.py
│   │
│   ├── tools/                   # reusable helpers, no agent logic
│   │   ├── llm.py               #   complete_json() + cost tracking + FakeLLM
│   │   ├── sandbox.py           #   safe subprocess runner
│   │   ├── sandbox_runner.py    #   the script that runs INSIDE the sandbox
│   │   ├── prompts.py           #   load prompts/<agent>/<version>.txt
│   │   └── batch.py             #   run one agent over a fixtures folder
│   │
│   ├── core/
│   │   └── recorder.py          # saves input/output/meta.json per call
│   │
│   ├── pipeline/
│   │   ├── simple.py            # Phase 3: plain loop
│   │   └── graph.py             # Phase 3: LangGraph version
│   │
│   ├── cli.py                   # Phase 4: `insight run ...`
│   └── api/                     # Phase 4 (later)
│       └── main.py
│
├── prompts/
│   ├── goal_parser/v1.txt
│   ├── planner/v1.txt
│   ├── code_writer/v1.txt
│   ├── checker/v1.txt
│   └── narrator/v1.txt
│
├── fixtures/
│   ├── data/                    # sales.csv, churn.csv, messy.csv, tiny.csv, wide.csv
│   ├── questions.yaml           # 15 questions + expected answers
│   ├── goal_parser/             # saved inputs for this agent (q01.json, ...)
│   ├── planner/
│   ├── code_writer/
│   └── narrator/
│
├── io_logs/                     # your filled I/O analysis tables (commit these!)
│   ├── profiler.md
│   ├── goal_parser.md
│   └── ...
│
├── runs/                        # auto-generated, git-ignored
│
├── tests/                       # fast unit tests, never call a real LLM
│   ├── test_schemas.py
│   ├── test_profiler.py
│   ├── test_sandbox.py
│   ├── test_checker_rules.py
│   └── test_assembler.py
│
├── eval/                        # Phase 6 (later)
├── Dockerfile                   # Phase 5 (later)
└── .github/workflows/ci.yml     # Phase 5 (later)
```

## Rules for this layout

1. `agents/` may import `schemas`, `tools`, `core`. **Never** `api`, `pipeline`, or a database.
2. `tools/` never imports `agents/`.
3. Each agent file has the same shape:

```python
"""Goal Parser — question + profile -> Goal."""
from insight_agent.schemas import GoalParserIn, Goal
from insight_agent.tools.llm import LLM, get_llm
from insight_agent.tools.prompts import load_prompt

PROMPT_VERSION = "v1"

def run(inp: GoalParserIn, llm: LLM | None = None) -> Goal:
    llm = llm or get_llm("cheap")
    system = load_prompt("goal_parser", PROMPT_VERSION)
    user = f"Columns: {...}\nQuestion: {inp.question}"
    goal = llm.complete_json(system=system, user=user, schema=Goal)
    return _fix_columns(goal, inp.profile)      # rule check after the LLM

if __name__ == "__main__":
    from insight_agent.tools.batch import cli_for
    cli_for(run, GoalParserIn, agent="goal_parser")   # --input file.json
```

4. `io_logs/*.md` **are committed** — they show your process and are great portfolio material.
5. `runs/` is **not** committed (too big, regenerated anytime).
