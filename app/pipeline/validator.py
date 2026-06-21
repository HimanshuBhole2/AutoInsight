"""Node 8: VALIDATOR — decide whether to retry code_writer or proceed."""

from __future__ import annotations

from typing import Any


def validator_node(state: dict[str, Any]) -> dict[str, Any]:
    verdict = state.get("critic_verdict", "pass")
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("config", {}).get("max_retries", 2)

    should_retry = (verdict == "retry") and (retry_count < max_retries)

    return {
        "should_retry": should_retry,
        "retry_count": retry_count + (1 if should_retry else 0),
    }
