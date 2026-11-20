# Agent Spec — `<agent name>`

Fill this in **before** writing code for a new agent (e.g. if you add one beyond the 10).

## Job (one sentence)

## Uses LLM?
- [ ] No — pure Python
- [ ] Yes — model tier: cheap / strong — prompt: `prompts/<agent>/v1.txt`

## Input model
```python
class XIn(BaseModel):
    ...
```

## Output model
```python
class XOut(BaseModel):
    ...
```

## Rules checked after the LLM (if any)
1.
2.

## Failure modes
| Failure | What the agent returns |
|---|---|
| | |

## Test inputs (10–15)
- clear cases:
- edge cases:
- adversarial / wrong cases:

## Done when
- [ ] ...
- [ ] ...
