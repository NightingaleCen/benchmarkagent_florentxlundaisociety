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


VALID_PROVIDERS: tuple[str, ...] = ("anthropic", "openai")


def parse_model_spec(model_id: str) -> tuple[str | None, str]:
    """Split a ``provider:model`` spec into parts.

    Returns ``(provider, model_name)``. If no colon is present, returns
    ``(None, model_id)`` and the caller should fall back to prefix detection
    or an explicit ``provider`` override.
    """
    if ":" in model_id:
        provider, name = model_id.split(":", 1)
        provider = provider.strip().lower()
        name = name.strip()
        if provider not in VALID_PROVIDERS:
            raise ValueError(
                f"unknown provider {provider!r} in model spec {model_id!r}. "
                f"supported: {list(VALID_PROVIDERS)}"
            )
        if not name:
            raise ValueError(f"empty model name in spec {model_id!r}")
        return provider, name
    return None, model_id


def _detect_provider(model_name: str) -> str | None:
    if model_name.startswith("claude-"):
        return "anthropic"
    if model_name.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    return None


def build_model_client(model_id: str, *, provider: str | None = None) -> ModelClient:
    """Construct a ``ModelClient`` for the given model identifier.

    Resolution order (highest precedence first):
      1. ``provider`` keyword argument (from CLI ``--provider`` flag).
      2. ``provider:model`` syntax in ``model_id`` (e.g. ``anthropic:my-custom``).
      3. Prefix detection on the model name (``claude-*``, ``gpt-*``, ``o1/o3/o4-*``).

    If none of these can decide, raise ``ValueError`` with a message telling
    the user how to disambiguate.
    """
    explicit_from_spec, model_name = parse_model_spec(model_id)

    if provider is not None:
        provider = provider.strip().lower()
        if provider not in VALID_PROVIDERS:
            raise ValueError(
                f"unknown provider override {provider!r}. "
                f"supported: {list(VALID_PROVIDERS)}"
            )
        chosen = provider
    elif explicit_from_spec is not None:
        chosen = explicit_from_spec
    else:
        detected = _detect_provider(model_name)
        if detected is None:
            raise ValueError(
                f"cannot determine provider for model {model_name!r}. "
                f"disambiguate by either prefixing the model "
                f"(`--model anthropic:{model_name}` or `--model openai:{model_name}`) "
                f"or passing `--provider anthropic|openai`."
            )
        chosen = detected

    if chosen == "anthropic":
        return AnthropicModelClient(model_name)
    if chosen == "openai":
        return OpenAIModelClient(model_name)
    raise ValueError(f"unhandled provider: {chosen!r}")
