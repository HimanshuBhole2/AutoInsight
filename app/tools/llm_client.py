"""
Thin wrappers around OpenAI and Anthropic clients.

Both expose a uniform `complete(messages, system, max_tokens) → str` interface
so nodes don't import SDK types directly. Retry logic lives here (tenacity).
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings

# ── OpenAI ────────────────────────────────────────────────────────────────────


class OpenAIClient:
    def __init__(self, api_key: str, model: str = "gpt-4o") -> None:
        import openai

        self._client = openai.OpenAI(api_key=api_key)
        self.model = model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def complete(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> str:
        all_messages = []
        if system:
            all_messages.append({"role": "system", "content": system})
        all_messages.extend(messages)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": all_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    def complete_json(
        self, messages: list[dict[str, str]], system: str | None = None, **kw: Any
    ) -> dict:
        raw = self.complete(messages, system=system, json_mode=True, **kw)
        return json.loads(raw)


# ── Anthropic ─────────────────────────────────────────────────────────────────


class AnthropicClient:
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6") -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def complete(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> str:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system

        response = self._client.messages.create(**kwargs)
        return response.content[0].text  # type: ignore[union-attr]

    def complete_json(
        self, messages: list[dict[str, str]], system: str | None = None, **kw: Any
    ) -> dict:
        raw = self.complete(messages, system=system, **kw)
        # Claude doesn't have native json_mode — strip any markdown fences
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())


# ── Singleton factories ───────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_openai_client(model: str = "gpt-4o") -> OpenAIClient:
    return OpenAIClient(api_key=get_settings().openai_api_key, model=model)


@lru_cache(maxsize=1)
def get_anthropic_client(model: str = "claude-sonnet-4-6") -> AnthropicClient:
    return AnthropicClient(api_key=get_settings().anthropic_api_key, model=model)
