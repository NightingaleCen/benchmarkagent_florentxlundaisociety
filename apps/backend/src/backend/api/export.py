from __future__ import annotations

import io
import zipfile

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from backend.api.sessions import get_store
from backend.sessions import SessionStore

router = APIRouter(prefix="/sessions/{sid}/export", tags=["export"])


@router.get("")
def export_zip(sid: str, store: SessionStore = Depends(get_store)):
    if not store.exists(sid):
        raise HTTPException(404, "session not found")
    session = store.get(sid)
    artifact = session.artifact_dir
    if not artifact.exists() or not any(artifact.rglob("*")):
        raise HTTPException(400, "artifact is empty — nothing to export")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in artifact.rglob("*"):
            if p.is_file():
                zf.write(p, arcname=p.relative_to(artifact))
    buf.seek(0)
    filename = f"benchmark-{sid}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
