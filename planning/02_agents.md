# 02 — Agent Specs (input → output for each agent)

Every agent follows the same pattern:

```python
def run(inp: AgentIn, *, llm: LLM | None = None) -> AgentOut: ...
```

- **Input and output are Pydantic models.** Nothing else goes in or out.
- The LLM client is **passed in** so tests can give a fake one.
- Each agent can be run alone from the command line:

```bash
python -m insight_agent.agents.profiler --input fixtures/profiler/sales.json
```

For each agent below you get: **Job · Input · Output · Tools · How to test · Done when**.

---

## 1. Profiler (no LLM)

**Job:** Read the CSV and describe it so later agents never have to see the raw data.

**Input**
```python
class ProfilerIn(BaseModel):
    csv_path: str
    sample_rows: int = 5
```

**Output**
```python
class ColumnInfo(BaseModel):
    name: str
    dtype: Literal["number", "text", "date", "bool", "category"]
    null_pct: float            # 0.0 – 1.0
    unique_count: int
    samples: list[str]         # max 5
    min: str | None = None     # for number/date
    max: str | None = None
    mean: float | None = None  # for number

class DataProfile(BaseModel):
    row_count: int
    col_count: int
    columns: list[ColumnInfo]
    head: list[dict]           # first N rows
    warnings: list[str]        # e.g. "column 'date' has 12% nulls"
```

**Tools:** pandas only.

**How to test:** 5 CSVs (clean, messy nulls, dates as strings, wide 50-col, tiny 3-row).
Check dtype detection by eye in the I/O log.

**Done when:** all 5 fixtures give correct dtypes; a 100k-row CSV profiles in < 2 s.

---

## 2. Goal Parser (LLM)

**Job:** Turn the user's question into a clear, structured goal using the real column names.

**Input**
```python
class GoalParserIn(BaseModel):
    question: str
    profile: DataProfile
```

**Output**
```python
class Goal(BaseModel):
    intent: Literal["compare", "trend", "distribution", "correlation",
                    "ranking", "summary", "anomaly"]
    restated_question: str          # clear version of the question
    target_columns: list[str]       # must exist in profile
    metrics_wanted: list[str]       # e.g. ["revenue growth %", "top region"]
    filters: list[str]              # e.g. ["year == 2024"]
    unknown_columns: list[str]      # user mentioned things not in data
    ambiguous: bool
```

**Tools:** LLM wrapper (JSON mode), prompt `prompts/goal_parser/v1.txt`.

**Rule check after LLM:** every `target_columns` item must be in `profile.columns`;
move any that aren't into `unknown_columns`.

**How to test:** 15 questions over 3 CSVs — easy, vague ("how are we doing?"), wrong column
("show profit" when there's no profit column).

**Done when:** ≥ 13/15 goals look right to you; zero invented column names after the rule check.

---

## 3. Planner (LLM)

**Job:** Break the goal into 1–5 small steps. Each step = one thing pandas can compute.

**Input**
```python
class PlannerIn(BaseModel):
    goal: Goal
    profile: DataProfile
    knowledge: list[str] = []       # empty until Phase 6 (RAG)
```

**Output**
```python
class PlanStep(BaseModel):
    step_id: str                    # "step1", "step2", ...
    description: str                # "Total revenue per region per year"
    expected_metrics: list[str]     # ["west_growth_pct", "east_growth_pct"]
    chart: Literal["none", "bar", "line", "scatter", "histogram", "pie"]

class Plan(BaseModel):
    steps: list[PlanStep]           # 1..5
    reasoning: str
```

**How to test:** same 15 questions. Read each plan: is it the *minimum* set of steps to answer?

**Done when:** no plan > 5 steps; ≥ 12/15 plans you'd accept as an analyst.

---

## 4. Code Writer (LLM)

**Job:** Write pandas code for **one** step. The code must put results in a `metrics` dict
and save a chart if asked.

**Input**
```python
class CodeWriterIn(BaseModel):
    step: PlanStep
    profile: DataProfile
    previous_attempt: str | None = None   # code that failed
    feedback: str | None = None           # error or checker feedback
```

**Output**
```python
class CodeOut(BaseModel):
    step_id: str
    code: str
    explanation: str
```

**Contract the code must follow** (put this in the prompt):
```python
# `df` is already loaded. Do not read files.
# Fill this dict with plain numbers/strings only:
metrics = {"west_growth_pct": 34.2, "top_region": "West"}
# Optional: tables
tables = {"revenue_by_region": some_df.head(20)}
# Optional: one chart, saved to CHART_PATH
plt.savefig(CHART_PATH)
```

**How to test:** feed it each step from the Planner fixtures, plus 5 "retry" cases with a fake
error message. Don't run the code yet — just read it. Then run it through the Executor.

**Done when:** ≥ 80% of steps run successfully on the first try; ≥ 90% after 1 retry.

---

## 5. Executor (no LLM — sandbox)

**Job:** Run the code safely and collect results.

**Input**
```python
class ExecutorIn(BaseModel):
    step_id: str
    code: str
    csv_path: str
    timeout_s: int = 30
```

**Output**
```python
class ExecResult(BaseModel):
    step_id: str
    success: bool
    metrics: dict[str, float | int | str]
    tables: dict[str, list[dict]]   # max 20 rows each
    chart_path: str | None
    stdout: str                     # capped 8 KB
    error: str | None               # traceback, capped
    duration_ms: int
```

**Tools:** `subprocess`, a small runner script, import allowlist (AST check), empty env,
timeout. (Reuse the *idea* from old `app/tools/sandbox.py`.)

**How to test:** hand-written code, no LLM needed:
good code · syntax error · `import os; os.environ` · infinite loop · `import requests` ·
huge print · no `metrics` dict.

**Done when:** all 7 cases behave correctly; no secret is ever visible inside the sandbox.

---

## 6. Checker (rules first, then optional LLM)

**Job:** Decide if a step result is good enough, and if not, say exactly why.

**Input**
```python
class CheckerIn(BaseModel):
    step: PlanStep
    code: str
    result: ExecResult
    attempt: int
    max_attempts: int = 3
```

**Output**
```python
class CheckVerdict(BaseModel):
    step_id: str
    verdict: Literal["pass", "retry", "give_up"]
    reasons: list[str]
    feedback_for_writer: str | None
```

**Rules (no LLM, run first):**
1. `success == False` → retry with the traceback.
2. `metrics` empty → retry ("you must fill metrics").
3. Any `expected_metrics` key missing → retry, naming the missing keys.
4. NaN / inf in metrics → retry.
5. `attempt >= max_attempts` → give_up.

**LLM (only if all rules pass, optional):** "Does this result answer the step description?"

**How to test:** build ExecResults by hand for each rule. Rules need no LLM, so these are
normal unit tests.

**Done when:** every rule has a unit test; the LLM check agrees with you on ≥ 8/10 cases
(or you decide to drop it — that's a valid outcome).

---

## 7. Narrator (LLM)

**Job:** Write the summary and insights. **Only cite numbers that are in `metrics`.**

**Input**
```python
class NarratorIn(BaseModel):
    question: str
    goal: Goal
    step_results: list[StepResult]    # step + final ExecResult + verdict
```

**Output**
```python
class Insight(BaseModel):
    title: str
    body: str                    # contains [m:step1.west_growth_pct]
    citations: list[str]         # ["step1.west_growth_pct"]
    chart_step_id: str | None

class Narrative(BaseModel):
    summary: str                 # 2–4 sentences, with citations
    insights: list[Insight]      # 1–5
    limitations: list[str]       # failed steps, unknown columns, small data, etc.
```

**How to test:** feed fixed `step_results` (saved from earlier runs). Count:
citations that don't exist, numbers written without citation, answers that miss the question.

**Done when:** 0 invalid citations across 10 fixtures; you'd send ≥ 8/10 to a manager.

---

## 8. Assembler (no LLM)

**Job:** Check citations, replace them with real values, build the final report.

**Input**
```python
class AssemblerIn(BaseModel):
    run_id: str
    question: str
    profile: DataProfile
    plan: Plan
    step_results: list[StepResult]
    narrative: Narrative
```

**Output**
```python
class Report(BaseModel):
    run_id: str
    question: str
    summary: str
    insights: list[Insight]
    charts: list[str]                # file paths
    limitations: list[str]
    citation_check: dict             # {"total": 9, "valid": 9, "invalid": []}
    markdown: str                    # the human-readable report
```

**Rule:** `[m:step1.west_growth_pct]` → `34.2%` (with a footnote to step1).
Invalid citation → remove the sentence and add to `citation_check.invalid`.

**How to test:** pure unit tests with hand-made narratives (valid, invalid, mixed).

**Done when:** invalid citations are always caught; the markdown opens nicely on GitHub.

---

## 9. Knowledge Retriever — Phase 6

**Job:** Given the goal, return up to 3 short domain notes (e.g. "churn rate = churned / start
customers") with similarity ≥ threshold. **Input:** `Goal` · **Output:** `list[KnowledgeHit]`.
Only add this when eval shows the Planner makes domain mistakes.

## 10. Memory Writer — Phase 6

**Job:** After a run that passes checks, save `(question, goal, plan, score)` so the
Retriever can show the Planner "a plan that worked before". **Input:** `Report` + `Plan` ·
**Output:** `saved: bool`.

---

## Shared helper type

```python
class StepResult(BaseModel):
    step: PlanStep
    attempts: list[CodeOut]
    final: ExecResult
    verdict: CheckVerdict
```
