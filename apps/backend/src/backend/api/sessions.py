from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.config import Settings, get_settings
from backend.sessions import SessionStore

router = APIRouter(prefix="/sessions", tags=["sessions"])


def get_store(settings: Settings = Depends(get_settings)) -> SessionStore:
    return SessionStore(settings.sessions_root)


class CreateSessionResponse(BaseModel):
    id: str


@router.post("", response_model=CreateSessionResponse)
def create_session(store: SessionStore = Depends(get_store)):
    session = store.create()
    return CreateSessionResponse(id=session.id)


@router.get("")
def list_sessions(store: SessionStore = Depends(get_store)):
    return {"ids": store.list_ids()}


@router.get("/{sid}")
def get_session(sid: str, store: SessionStore = Depends(get_store)):
    if not store.exists(sid):
        raise HTTPException(status_code=404, detail="session not found")
    session = store.get(sid)
    return {
        "id": session.id,
        "files": session.list_artifact_files(),
        "chat_entries": sum(1 for _ in session.iter_chat()),
    }


@router.delete("/{sid}")
def delete_session(sid: str, store: SessionStore = Depends(get_store)):
    if not store.exists(sid):
        raise HTTPException(status_code=404, detail="session not found")
    store.delete(sid)
    return {"ok": True}
