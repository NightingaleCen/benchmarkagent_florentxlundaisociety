"""Orchestrator agent: drives a tool loop against the configured LLM provider.

Supports both Anthropic (claude-* models) and OpenAI-compatible APIs (everything
else, including custom base URLs set via OPENAI_BASE_URL).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace as _NS
from typing import Any

import anthropic

from backend.agent.tools import ToolSpec, build_tools, tools_to_anthropic_format
from backend.config import Settings, get_settings
from backend.sessions import Session

_PROMPT_PATH = Path(__file__).parent / "prompts" / "orchestrator.md"


def _system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _build_system_prompt(*, allow_agent_data_access: bool) -> str:
    # Keep for backwards compatibility
    return _system_prompt()


def _detect_provider(model: str) -> str:
    """Return 'anthropic' for claude-* or anthropic:-prefixed models, else 'openai'."""
    if model.startswith("claude-") or model.startswith("anthropic:"):
        return "anthropic"
    return "openai"


def _strip_provider_prefix(model: str) -> str:
    """Remove 'anthropic:' or 'openai:' prefix if present."""
    if ":" in model:
        prefix, rest = model.split(":", 1)
        if prefix.lower() in ("anthropic", "openai"):
            return rest
    return model


def _tools_to_openai_format(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get(
                    "input_schema", {"type": "object", "properties": {}}
                ),
            },
        }
        for t in tools
    ]


@dataclass
class AgentEvent:
    """One event to stream back to the client."""

    kind: str  # "assistant_text" | "tool_use" | "tool_result" | "done" | "error"
    data: dict[str, Any]


async def run_turn(
    session: Session,
    user_message: str,
    *,
    settings: Settings | None = None,
    model_override: str | None = None,
    allow_agent_data_access: bool = True,
) -> AsyncIterator[AgentEvent]:
    """Drive one user turn: append their message, run the tool loop until the
    assistant stops requesting tools, append every event, yield as it goes.

    ``model_override`` (if given) takes precedence over ``settings.orchestrator_model``
    for this turn only. Supports both Anthropic (claude-*) and OpenAI-compatible
    models (everything else, including custom OPENAI_BASE_URL endpoints).
    """
    settings = settings or get_settings()
    model_raw = model_override or settings.orchestrator_model
    provider = _detect_provider(model_raw)
    model = _strip_provider_prefix(model_raw)

    if provider == "anthropic":
        client: Any = anthropic.AsyncAnthropic()
    else:
        import openai as _openai

        client = _openai.AsyncOpenAI()

    tools = build_tools(session, allow_agent_data_access=allow_agent_data_access)
    tool_index: dict[str, ToolSpec] = {t.name: t for t in tools}

    system = _build_system_prompt(allow_agent_data_access=allow_agent_data_access)
    anthropic_tool_specs = tools_to_anthropic_format(tools)

    session.append_chat({"role": "user", "content": user_message, "model": model})

    if provider == "anthropic":
        history = _load_history_anthropic(session)
        tool_specs: list[dict] = anthropic_tool_specs
    else:
        history = _load_history_openai(session)
        tool_specs = _tools_to_openai_format(anthropic_tool_specs)

    async for event in _drive_loop(
        session,
        client,
        provider,
        model,
        tool_index,
        tool_specs,
        system,
        history,
        settings.max_agent_iterations,
    ):
        yield event


async def resume_turn(
    session: Session,
    *,
    settings: Settings | None = None,
    model_override: str | None = None,
    allow_agent_data_access: bool = True,
) -> AsyncIterator[AgentEvent]:
    """Continue a turn that was paused due to hitting the iteration limit.

    Does not append a new user message — picks up from the existing history.
    """
    settings = settings or get_settings()
    model_raw = model_override or settings.orchestrator_model
    provider = _detect_provider(model_raw)
    model = _strip_provider_prefix(model_raw)

    if provider == "anthropic":
        client: Any = anthropic.AsyncAnthropic()
    else:
        import openai as _openai

        client = _openai.AsyncOpenAI()

    tools = build_tools(session, allow_agent_data_access=allow_agent_data_access)
    tool_index: dict[str, ToolSpec] = {t.name: t for t in tools}

    system = _build_system_prompt(allow_agent_data_access=allow_agent_data_access)
    anthropic_tool_specs = tools_to_anthropic_format(tools)

    if provider == "anthropic":
        history = _load_history_anthropic(session)
        tool_specs: list[dict] = anthropic_tool_specs
    else:
        history = _load_history_openai(session)
        tool_specs = _tools_to_openai_format(anthropic_tool_specs)

    async for event in _drive_loop(
        session,
        client,
        provider,
        model,
        tool_index,
        tool_specs,
        system,
        history,
        settings.max_agent_iterations,
    ):
        yield event


async def _drive_loop(
    session: Session,
    client: Any,
    provider: str,
    model: str,
    tool_index: dict[str, ToolSpec],
    tool_specs: list[dict],
    system: str,
    history: list[dict],
    max_iterations: int,
) -> AsyncIterator[AgentEvent]:
    """Core tool loop shared by run_turn and resume_turn."""
    for iteration in range(max_iterations):
        try:
            if provider == "anthropic":
                # Iterate raw stream events so we can:
                #   a) stream text chunks immediately as assistant_text
                #   b) emit tool_use as soon as the block starts (name is known,
                #      input is still being generated) — eliminates the "frozen"
                #      experience on tool-calling turns.
                _previewed_tool_ids: set[str] = set()
                async with client.messages.stream(
                    model=model,
                    max_tokens=4096,
                    system=system,
                    tools=tool_specs,
                    messages=history,
                ) as stream:
                    async for event in stream:
                        etype = getattr(event, "type", None)
                        if etype == "content_block_start":
                            cb = getattr(event, "content_block", None)
                            if cb is not None and getattr(cb, "type", None) == "tool_use":
                                _previewed_tool_ids.add(cb.id)
                                yield AgentEvent(
                                    "tool_use",
                                    {
                                        "type": "tool_use",
                                        "id": cb.id,
                                        "name": cb.name,
                                        "input": {},
                                    },
                                )
                        elif etype == "content_block_delta":
                            delta = getattr(event, "delta", None)
                            if delta is not None:
                                dtype = getattr(delta, "type", None)
                                if dtype == "text_delta":
                                    yield AgentEvent(
                                        "assistant_text", {"text": delta.text}
                                    )
                    response = await stream.get_final_message()
            else:
                # OpenAI-compatible streaming — stream text and emit tool_use
                # early (by name) just like the Anthropic path.
                openai_messages = [{"role": "system", "content": system}] + history
                _oi_text_buf = ""
                _oi_tool_map: dict[int, dict] = {}
                _oi_finish_reason: str | None = None
                _oi_previewed_indices: set[int] = set()

                stream_obj = await client.chat.completions.create(
                    model=model,
                    messages=openai_messages,
                    tools=tool_specs,
                    stream=True,
                )
                async for chunk in stream_obj:
                    choice = chunk.choices[0] if chunk.choices else None
                    if not choice:
                        continue
                    if choice.finish_reason:
                        _oi_finish_reason = choice.finish_reason
                    delta = choice.delta
                    if delta.content:
                        _oi_text_buf += delta.content
                        yield AgentEvent("assistant_text", {"text": delta.content})
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in _oi_tool_map:
                                name = (
                                    tc.function.name
                                    if tc.function and tc.function.name
                                    else ""
                                )
                                _oi_tool_map[idx] = {
                                    "id": tc.id or "",
                                    "name": name,
                                    "args": "",
                                }
                                if name:
                                    _oi_previewed_indices.add(idx)
                                    yield AgentEvent(
                                        "tool_use",
                                        {
                                            "type": "tool_use",
                                            "id": _oi_tool_map[idx]["id"],
                                            "name": name,
                                            "input": {},
                                        },
                                    )
                            else:
                                if tc.id:
                                    _oi_tool_map[idx]["id"] = tc.id
                                if tc.function:
                                    if tc.function.name:
                                        _oi_tool_map[idx]["name"] += tc.function.name
                                    if tc.function.arguments:
                                        _oi_tool_map[idx]["args"] += (
                                            tc.function.arguments
                                        )

                # Reconstruct a response-like namespace for the post-processing
                # code below, which was written for the non-streaming case.
                _oi_tc_ns = (
                    [
                        _NS(
                            id=tc["id"],
                            function=_NS(name=tc["name"], arguments=tc["args"]),
                        )
                        for tc in _oi_tool_map.values()
                    ]
                    if _oi_tool_map
                    else None
                )
                response = _NS(
                    choices=[
                        _NS(
                            message=_NS(
                                content=_oi_text_buf if _oi_text_buf else None,
                                tool_calls=_oi_tc_ns,
                            ),
                            finish_reason=_oi_finish_reason,
                        )
                    ]
                )
        except BaseException as e:
            if not isinstance(e, Exception):
                raise
            err = {"message": str(e)}
            session.append_chat({"role": "error", "content": err})
            yield AgentEvent("error", err)
            return

        if provider == "anthropic":
            assistant_blocks: list[dict] = []
            tool_uses: list[dict] = []

            for block in response.content:
                if block.type == "text":
                    text = block.text
                    assistant_blocks.append({"type": "text", "text": text})
                    session.append_chat({"role": "assistant", "content": text})
                    # Text already emitted chunk-by-chunk during streaming above.
                elif block.type == "tool_use":
                    tu = {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                    assistant_blocks.append(tu)
                    tool_uses.append(tu)
                    session.append_chat({"role": "tool_use", "content": tu})
                    if block.id not in _previewed_tool_ids:
                        # Only emit if not already previewed during streaming.
                        yield AgentEvent("tool_use", tu)

            history.append({"role": "assistant", "content": assistant_blocks})

            if response.stop_reason != "tool_use" or not tool_uses:
                yield AgentEvent("done", {"stop_reason": response.stop_reason})
                return

            tool_results: list[dict] = []
            for tu in tool_uses:
                result_str = _run_tool(tool_index, tu)
                tr = {
                    "type": "tool_result",
                    "tool_use_id": tu["id"],
                    "content": result_str,
                }
                tool_results.append(tr)
                session.append_chat(
                    {
                        "role": "tool_result",
                        "content": {
                            "name": tu["name"],
                            "result": result_str,
                            "tool_use_id": tu["id"],
                        },
                    }
                )
                yield AgentEvent(
                    "tool_result", {"name": tu["name"], "result": result_str}
                )

            history.append({"role": "user", "content": tool_results})

        else:
            # OpenAI-compatible response handling
            msg = response.choices[0].message
            finish_reason = response.choices[0].finish_reason
            tool_uses_openai: list[dict] = []

            native_assistant: dict[str, Any] = {
                "role": "assistant",
                "content": msg.content,
            }
            if msg.tool_calls:
                native_assistant["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]

            if msg.content:
                session.append_chat({"role": "assistant", "content": msg.content})
                # Text already emitted chunk-by-chunk during streaming above.

            if msg.tool_calls:
                for idx, tc in enumerate(msg.tool_calls):
                    try:
                        input_data = json.loads(tc.function.arguments)
                    except Exception:
                        input_data = {}
                    tu = {
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.function.name,
                        "input": input_data,
                    }
                    tool_uses_openai.append(tu)
                    session.append_chat({"role": "tool_use", "content": tu})
                    if idx not in _oi_previewed_indices:
                        # Only emit if not already previewed during streaming.
                        yield AgentEvent("tool_use", tu)

            history.append(native_assistant)

            if finish_reason != "tool_calls" or not tool_uses_openai:
                yield AgentEvent("done", {"stop_reason": finish_reason})
                return

            for tu in tool_uses_openai:
                result_str = _run_tool(tool_index, tu)
                history.append(
                    {"role": "tool", "tool_call_id": tu["id"], "content": result_str}
                )
                session.append_chat(
                    {
                        "role": "tool_result",
                        "content": {
                            "name": tu["name"],
                            "result": result_str,
                            "tool_use_id": tu["id"],
                        },
                    }
                )
                yield AgentEvent(
                    "tool_result", {"name": tu["name"], "result": result_str}
                )

    cont = {"used_iterations": max_iterations, "model": model}
    session.append_chat({"role": "continuation_required", "content": cont})
    yield AgentEvent("continuation_required", cont)


def _run_tool(tool_index: dict[str, ToolSpec], tu: dict) -> str:
    handler = tool_index.get(tu["name"])
    if handler is None:
        return _err_json(f"unknown tool: {tu['name']}")
    try:
        return handler.handler(tu["input"])
    except Exception as e:
        return _err_json(f"tool raised: {e}")


def _load_history_anthropic(session: Session) -> list[dict]:
    """Reconstruct Anthropic-API-ready message history from the session chat log."""
    history: list[dict] = []
    current_assistant: list[dict] | None = None
    pending_tool_results: list[dict] = []

    for entry in session.iter_chat():
        role = entry.get("role")
        content = entry.get("content")
        if role == "user":
            if pending_tool_results:
                history.append({"role": "user", "content": pending_tool_results})
                pending_tool_results = []
            if current_assistant is not None:
                history.append({"role": "assistant", "content": current_assistant})
                current_assistant = None
            history.append({"role": "user", "content": content})
        elif role == "assistant":
            if current_assistant is None:
                current_assistant = []
            current_assistant.append({"type": "text", "text": content})
        elif role == "tool_use":
            if current_assistant is None:
                current_assistant = []
            current_assistant.append(content)
        elif role == "tool_result":
            if current_assistant is not None:
                history.append({"role": "assistant", "content": current_assistant})
                current_assistant = None
            pending_tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": content.get("tool_use_id", ""),
                    "content": content.get("result", ""),
                }
            )
    if current_assistant is not None:
        history.append({"role": "assistant", "content": current_assistant})
    if pending_tool_results:
        history.append({"role": "user", "content": pending_tool_results})
    return history


def _load_history_openai(session: Session) -> list[dict]:
    """Reconstruct OpenAI-API-ready message history from the session chat log."""
    history: list[dict] = []
    pending_tool_calls: list[dict] = []

    def flush_tool_calls() -> None:
        if pending_tool_calls:
            history.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": list(pending_tool_calls),
                }
            )
            pending_tool_calls.clear()

    for entry in session.iter_chat():
        role = entry.get("role")
        content = entry.get("content")
        if role == "user":
            flush_tool_calls()
            history.append({"role": "user", "content": content})
        elif role == "assistant":
            flush_tool_calls()
            history.append({"role": "assistant", "content": content})
        elif role == "tool_use":
            pending_tool_calls.append(
                {
                    "id": content.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": content.get("name", ""),
                        "arguments": json.dumps(content.get("input", {})),
                    },
                }
            )
        elif role == "tool_result":
            flush_tool_calls()
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": content.get("tool_use_id", ""),
                    "content": content.get("result", ""),
                }
            )
    flush_tool_calls()
    return history


def _err_json(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg})
