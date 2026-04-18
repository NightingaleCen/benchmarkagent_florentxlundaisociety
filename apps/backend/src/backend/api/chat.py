from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend.agent.orchestrator import resume_turn, run_turn
from backend.api.sessions import get_store
from backend.sessions import SessionStore

router = APIRouter(prefix="/sessions/{sid}", tags=["chat"])


class MessageBody(BaseModel):
    content: str
    model: str | None = None  # per-turn override for the orchestrator model
    allow_agent_data_access: bool = True


@router.get("/messages")
def get_messages(sid: str, store: SessionStore = Depends(get_store)):
    if not store.exists(sid):
        raise HTTPException(404, "session not found")
    return {"entries": list(store.get(sid).iter_chat())}


@router.post("/messages")
async def post_message(
    sid: str, body: MessageBody, store: SessionStore = Depends(get_store)
):
    if not store.exists(sid):
        raise HTTPException(404, "session not found")
    session = store.get(sid)

    async def event_stream():
        try:
            async for event in run_turn(
                session,
                body.content,
                model_override=body.model,
                allow_agent_data_access=body.allow_agent_data_access,
            ):
                yield {
                    "event": event.kind,
                    "data": json.dumps(event.data, ensure_ascii=False),
                }
        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"message": str(e)}),
            }

    return EventSourceResponse(event_stream())


class ContinueBody(BaseModel):
    model: str | None = None
    allow_agent_data_access: bool = True


@router.post("/messages/continue")
async def continue_turn(
    sid: str, body: ContinueBody, store: SessionStore = Depends(get_store)
):
    if not store.exists(sid):
        raise HTTPException(404, "session not found")
    session = store.get(sid)

    async def event_stream():
        try:
            async for event in resume_turn(
                session,
                model_override=body.model,
                allow_agent_data_access=body.allow_agent_data_access,
            ):
                yield {
                    "event": event.kind,
                    "data": json.dumps(event.data, ensure_ascii=False),
                }
        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"message": str(e)}),
            }

    return EventSourceResponse(event_stream())
