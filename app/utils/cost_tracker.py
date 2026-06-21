"""Token counter and $/run cost calculator."""

from __future__ import annotations

from dataclasses import dataclass, field

# Prices per 1M tokens as of 2025-Q4 (input / output)
_PRICE_PER_1M: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5-20251001": (0.25, 1.25),
    "text-embedding-3-small": (0.02, 0.00),
}


@dataclass
class ModelUsage:
    model: str
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def cost_usd(self) -> float:
        prices = _PRICE_PER_1M.get(self.model, (0.0, 0.0))
        return (self.input_tokens * prices[0] + self.output_tokens * prices[1]) / 1_000_000


@dataclass
class RunCostTracker:
    usages: list[ModelUsage] = field(default_factory=list)

    def record(self, model: str, input_tokens: int, output_tokens: int) -> None:
        self.usages.append(ModelUsage(model, input_tokens, output_tokens))

    @property
    def total_cost_usd(self) -> float:
        return sum(u.cost_usd for u in self.usages)

    @property
    def total_input_tokens(self) -> int:
        return sum(u.input_tokens for u in self.usages)

    @property
    def total_output_tokens(self) -> int:
        return sum(u.output_tokens for u in self.usages)

    def summary(self) -> dict:
        return {
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "by_model": [
                {
                    "model": u.model,
                    "input_tokens": u.input_tokens,
                    "output_tokens": u.output_tokens,
                    "cost_usd": round(u.cost_usd, 6),
                }
                for u in self.usages
            ],
        }
