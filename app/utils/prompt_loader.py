"""Versioned prompt file loader.

Prompts live in prompts/v{N}/{name}.txt.
Change the version prefix when a prompt breaks backwards compatibility.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_PROMPTS_ROOT = Path(__file__).parent.parent.parent / "prompts"
_DEFAULT_VERSION = "v1"


@lru_cache(maxsize=64)
def load_prompt(name: str, version: str = _DEFAULT_VERSION) -> str:
    """Load and cache a prompt file. Raises FileNotFoundError if missing."""
    path = _PROMPTS_ROOT / version / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def load_prompt_safe(name: str, version: str = _DEFAULT_VERSION, default: str = "") -> str:
    """Like load_prompt but returns default instead of raising."""
    try:
        return load_prompt(name, version)
    except FileNotFoundError:
        return default
