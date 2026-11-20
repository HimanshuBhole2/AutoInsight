# I/O Log — `<agent name>`

Copy this file to `io_logs/<agent>.md` in the new repo and fill it in.

## Setup

| | |
|---|---|
| Agent | `<agent>` |
| Prompt version | v1 |
| Model | |
| Date | |
| Fixtures used | `fixtures/<agent>/*.json` (N = ) |

## Results — v1

| id | input (short) | expected | actual output (short) | ok? | tokens | ms | notes |
|---|---|---|---|---|---|---|---|
| q01 | | | | ✅/❌ | | | |
| q02 | | | | | | | |
| q03 | | | | | | | |

**Score:** __ / __   **Avg cost:** $___   **Avg latency:** ___ ms

## Patterns in the failures

- e.g. "Vague questions are never marked ambiguous"
- e.g. "Uses `Revenue` instead of `revenue` (case)"

## Change made for v2

- Prompt change: ...
- Code / rule change: ...

## Results — v2

| id | ok? | changed vs v1? | notes |
|---|---|---|---|
| q01 | | | |

**Score:** __ / __

## Decision

- [ ] "Done when" from 02_agents.md met → freeze, save outputs as next agent's fixtures
- [ ] Not yet → next change: ...
