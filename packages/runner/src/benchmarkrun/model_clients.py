"""Minimum portable abstraction for calling LLM providers.

Adapters receive a ModelClient from the runner. The interface exposes a small
shared surface (``complete``, ``messages``) plus a ``raw_client`` escape hatch
for provider-specific features. Provider SDKs must still be declared in the
artifact's ``runtime.requirements``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass
class CompletionResponse:
    text: str
    input_tokens: int
    output_tokens: int
    raw: Any


@runtime_checkable
class ModelClient(Protocol):
    model_id: str
    raw_client: Any

    def complete(self, prompt: str, **kwargs: Any) -> CompletionResponse: ...

    def messages(
        self, messages: list[dict], **kwargs: Any
    ) -> CompletionResponse: ...


class AnthropicModelClient:
    def __init__(self, model_id: str) -> None:
        import anthropic

        self.model_id = model_id
        self.raw_client = anthropic.Anthropic()

    def complete(self, prompt: str, **kwargs: Any) -> CompletionResponse:
        return self.messages([{"role": "user", "content": prompt}], **kwargs)

    def messages(
        self, messages: list[dict], **kwargs: Any
    ) -> CompletionResponse:
        max_tokens = kwargs.pop("max_tokens", 1024)
        resp = self.raw_client.messages.create(
            model=self.model_id,
            max_tokens=max_tokens,
            messages=messages,
            **kwargs,
        )
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        )
        return CompletionResponse(
            text=text,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            raw=resp.model_dump() if hasattr(resp, "model_dump") else resp,
        )


class OpenAIModelClient:
    def __init__(self, model_id: str) -> None:
        import openai

        self.model_id = model_id
        self.raw_client = openai.OpenAI()

    def complete(self, prompt: str, **kwargs: Any) -> CompletionResponse:
        return self.messages([{"role": "user", "content": prompt}], **kwargs)

    def messages(
        self, messages: list[dict], **kwargs: Any
    ) -> CompletionResponse:
        resp = self.raw_client.chat.completions.create(
            model=self.model_id,
            messages=messages,
            **kwargs,
        )
        choice = resp.choices[0]
        return CompletionResponse(
            text=choice.message.content or "",
            input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            output_tokens=resp.usage.completion_tokens if resp.usage else 0,
            raw=resp.model_dump() if hasattr(resp, "model_dump") else resp,
        )


def build_model_client(model_id: str) -> ModelClient:
    """Factory: decide provider from the model_id string.

    Anthropic: model IDs starting with ``claude-``.
    OpenAI: model IDs starting with ``gpt-`` or ``o`` (o1, o3, o4-...).
    """
    if model_id.startswith("claude-"):
        return AnthropicModelClient(model_id)
    if model_id.startswith(("gpt-", "o1", "o3", "o4")):
        return OpenAIModelClient(model_id)
    raise ValueError(
        f"unrecognized model id: {model_id!r}. "
        f"MVP supports claude-* (Anthropic) and gpt-*/o* (OpenAI)."
    )
