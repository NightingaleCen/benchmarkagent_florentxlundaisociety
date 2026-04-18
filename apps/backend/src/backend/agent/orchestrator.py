"""Orchestrator agent: drives a tool loop against Anthropic's API.

Note: CLAUDE.md names Claude Agent SDK as the long-term target. For MVP we use
the Anthropic SDK directly — it gives us clean control of the tool loop and
SSE streaming without extra infra. The tool surface matches what we'd expose
via Agent SDK, so migration later is a localized change.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic

from backend.agent.tools import ToolSpec, build_tools, tools_to_anthropic_format
from backend.config import Settings, get_settings
from backend.sessions import Session

_PROMPT_PATH = Path(__file__).parent / "prompts" / "orchestrator.md"


def _system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


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
) -> AsyncIterator[AgentEvent]:
    """Drive one user turn: append their message, run the tool loop until the
    assistant stops requesting tools, append every event, yield as it goes.

    ``model_override`` (if given) takes precedence over ``settings.orchestrator_model``
    for this turn only. Typical use: the frontend lets the user pick a model per
    session and passes it with each chat request.
    """
    settings = settings or get_settings()
    model = model_override or settings.orchestrator_model
    client = anthropic.AsyncAnthropic()
    tools = build_tools(session)
    tool_index: dict[str, ToolSpec] = {t.name: t for t in tools}

    history = _load_history(session)
    history.append({"role": "user", "content": user_message})
    session.append_chat({"role": "user", "content": user_message, "model": model})

    system = _system_prompt()
    tool_specs = tools_to_anthropic_format(tools)

    for iteration in range(settings.max_agent_iterations):
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=4096,
                system=system,
                tools=tool_specs,
                messages=history,
            )
        except Exception as e:
            err = {"message": str(e)}
            session.append_chat({"role": "error", "content": err})
            yield AgentEvent("error", err)
            return

        assistant_blocks: list[dict] = []
        tool_uses: list[dict] = []
        for block in response.content:
            if block.type == "text":
                text = block.text
                assistant_blocks.append({"type": "text", "text": text})
                session.append_chat({"role": "assistant", "content": text})
                yield AgentEvent("assistant_text", {"text": text})
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
                yield AgentEvent("tool_use", tu)

        history.append({"role": "assistant", "content": assistant_blocks})

        if response.stop_reason != "tool_use" or not tool_uses:
            yield AgentEvent("done", {"stop_reason": response.stop_reason})
            return

        tool_results: list[dict] = []
        for tu in tool_uses:
            handler = tool_index.get(tu["name"])
            if handler is None:
                result_str = _err_json(f"unknown tool: {tu['name']}")
            else:
                try:
                    result_str = handler.handler(tu["input"])
                except Exception as e:
                    result_str = _err_json(f"tool raised: {e}")
            tr = {
                "type": "tool_result",
                "tool_use_id": tu["id"],
                "content": result_str,
            }
            tool_results.append(tr)
            session.append_chat(
                {"role": "tool_result", "content": {"name": tu["name"], "result": result_str}}
            )
            yield AgentEvent("tool_result", {"name": tu["name"], "result": result_str})

        history.append({"role": "user", "content": tool_results})

    err = {"message": f"agent exceeded max iterations ({settings.max_agent_iterations})"}
    session.append_chat({"role": "error", "content": err})
    yield AgentEvent("error", err)


def _load_history(session: Session) -> list[dict]:
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


def _err_json(msg: str) -> str:
    import json

    return json.dumps({"ok": False, "error": msg})
