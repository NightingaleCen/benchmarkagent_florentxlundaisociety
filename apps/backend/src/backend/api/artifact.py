from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.sessions import get_store
from backend.sessions import SessionStore

router = APIRouter(prefix="/sessions/{sid}/artifact", tags=["artifact"])


class WriteBody(BaseModel):
    content: str


@router.get("")
def list_files(sid: str, store: SessionStore = Depends(get_store)):
    if not store.exists(sid):
        raise HTTPException(404, "session not found")
    return {"files": store.get(sid).list_artifact_files()}


@router.get("/{path:path}")
def read_file(sid: str, path: str, store: SessionStore = Depends(get_store)):
    if not store.exists(sid):
        raise HTTPException(404, "session not found")
    try:
        content = store.get(sid).read_artifact_file(path)
    except FileNotFoundError:
        raise HTTPException(404, f"file not found: {path}")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"path": path, "content": content}


@router.put("/{path:path}")
def write_file(
    sid: str, path: str, body: WriteBody, store: SessionStore = Depends(get_store)
):
    if not store.exists(sid):
        raise HTTPException(404, "session not found")
    try:
        store.get(sid).write_artifact_file(path, body.content)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "path": path}
