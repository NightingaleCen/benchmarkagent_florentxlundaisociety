from __future__ import annotations

import io
import shutil
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from backend.api.sessions import get_store
from backend.sessions import SessionStore

router = APIRouter(prefix="/sessions/{sid}/export", tags=["export"])


def _should_ignore_artifact_path(path: str | Path) -> bool:
    p = Path(path)
    return "__pycache__" in p.parts or p.suffix in {".pyc", ".pyo"}


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
            if p.is_file() and not _should_ignore_artifact_path(
                p.relative_to(artifact)
            ):
                zf.write(p, arcname=p.relative_to(artifact))
    buf.seek(0)
    filename = f"benchmark-{sid}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import")
async def import_zip(
    sid: str, file: UploadFile = File(...), store: SessionStore = Depends(get_store)
):
    if not store.exists(sid):
        raise HTTPException(404, "session not found")
    session = store.get(sid)

    try:
        payload = await file.read()
        zf = zipfile.ZipFile(io.BytesIO(payload))
    except Exception as e:
        raise HTTPException(400, f"invalid zip file: {e}")

    if session.artifact_dir.exists():
        shutil.rmtree(session.artifact_dir)
    session.artifact_dir.mkdir(parents=True, exist_ok=True)

    imported: list[str] = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        rel = info.filename.lstrip("/")
        if not rel:
            continue
        if _should_ignore_artifact_path(rel):
            continue
        try:
            content = zf.read(info).decode("utf-8")
            session.write_artifact_file(rel, content)
            imported.append(rel)
        except Exception as e:
            raise HTTPException(400, f"failed to import {info.filename!r}: {e}")

    if not imported:
        raise HTTPException(400, "zip archive is empty")

    return {"ok": True, "files": sorted(imported)}
