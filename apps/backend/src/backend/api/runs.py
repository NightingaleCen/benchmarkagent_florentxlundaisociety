from __future__ import annotations

import asyncio
import io
import json
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from benchmarkrun.loader import load_artifact
from benchmarkrun.runtime import run_benchmark_iter

from backend.api.sessions import get_store
from backend.sessions import SessionStore

router = APIRouter(prefix="/sessions/{sid}/runs", tags=["runs"])

_ALLOWED_RUN_FILES = {"results.jsonl", "summary.json"}


class RunRequest(BaseModel):
    model: str
    limit: int | None = None
    provider: str | None = None


@router.post("")
async def trigger_run(
    sid: str, body: RunRequest, store: SessionStore = Depends(get_store)
):
    if not store.exists(sid):
        raise HTTPException(404, "session not found")
    session = store.get(sid)

    try:
        artifact = load_artifact(session.artifact_dir)
    except Exception as e:
        raise HTTPException(400, f"artifact failed to load: {e}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = session.runs_dir / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    status_file = out_dir / "status.json"
    started_at = datetime.now(timezone.utc).isoformat()
    _write_status(status_file, {
        "run_id": stamp,
        "status": "running",
        "model": body.model,
        "limit": body.limit,
        "started_at": started_at,
        "progress": {"done": 0, "total": None, "passed": 0, "failed": 0, "errored": 0},
    })

    loop = asyncio.get_event_loop()
    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    def _run_sync() -> None:
        try:
            for event in run_benchmark_iter(
                artifact,
                model_id=body.model,
                out_dir=out_dir,
                limit=body.limit,
                provider=body.provider,
            ):
                if event["event"] == "sample":
                    _write_status(status_file, {
                        "run_id": stamp,
                        "status": "running",
                        "model": body.model,
                        "started_at": started_at,
                        "progress": {
                            "done": event["done"],
                            "total": event["total"],
                            "passed": event["passed"],
                            "failed": event["failed"],
                            "errored": event["errored"],
                        },
                    })
                elif event["event"] == "done":
                    # summary.json written by runner; status.json no longer needed
                    status_file.unlink(missing_ok=True)

                asyncio.run_coroutine_threadsafe(queue.put(event), loop)
        except Exception as exc:
            _write_status(status_file, {
                "run_id": stamp,
                "status": "failed",
                "model": body.model,
                "started_at": started_at,
                "error": str(exc),
            })
            asyncio.run_coroutine_threadsafe(
                queue.put({"event": "error", "message": str(exc)}), loop
            )
        finally:
            asyncio.run_coroutine_threadsafe(queue.put(None), loop)

    loop.run_in_executor(None, _run_sync)

    async def event_stream():
        while True:
            item = await queue.get()
            if item is None:
                break
            yield {
                "event": item.get("event", "unknown"),
                "data": json.dumps(item, default=str, ensure_ascii=False),
            }

    return EventSourceResponse(event_stream())


@router.get("")
def list_runs(sid: str, store: SessionStore = Depends(get_store)):
    if not store.exists(sid):
        raise HTTPException(404, "session not found")
    session = store.get(sid)
    runs: list[dict] = []
    if session.runs_dir.exists():
        for run_dir in sorted(session.runs_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            summary_file = run_dir / "summary.json"
            status_file = run_dir / "status.json"
            if summary_file.exists():
                runs.append({
                    "run_id": run_dir.name,
                    "status": "completed",
                    "summary": json.loads(summary_file.read_text()),
                    "progress": None,
                })
            elif status_file.exists():
                try:
                    data = json.loads(status_file.read_text())
                except Exception:
                    data = {}
                runs.append({
                    "run_id": run_dir.name,
                    "status": data.get("status", "unknown"),
                    "summary": None,
                    "progress": data.get("progress"),
                    "model": data.get("model"),
                    "started_at": data.get("started_at"),
                    "error": data.get("error"),
                })
    return {"runs": runs}


@router.get("/{run_id}")
def get_run(sid: str, run_id: str, store: SessionStore = Depends(get_store)):
    if not store.exists(sid):
        raise HTTPException(404, "session not found")
    run_dir = store.get(sid).runs_dir / run_id
    summary_file = run_dir / "summary.json"
    results_file = run_dir / "results.jsonl"
    if not summary_file.exists():
        raise HTTPException(404, "run not found or not yet completed")
    results = []
    if results_file.exists():
        for line in results_file.read_text().splitlines():
            if line.strip():
                results.append(json.loads(line))
    return {
        "run_id": run_id,
        "summary": json.loads(summary_file.read_text()),
        "results": results,
    }


@router.get("/{run_id}/files/{name}")
def download_run_file(
    sid: str, run_id: str, name: str, store: SessionStore = Depends(get_store)
):
    if name not in _ALLOWED_RUN_FILES:
        raise HTTPException(400, f"file must be one of: {', '.join(sorted(_ALLOWED_RUN_FILES))}")
    if not store.exists(sid):
        raise HTTPException(404, "session not found")
    runs_dir = store.get(sid).runs_dir
    run_dir = (runs_dir / run_id).resolve()
    if not run_dir.is_relative_to(runs_dir.resolve()):
        raise HTTPException(400, "invalid run_id")
    target = run_dir / name
    if not target.exists():
        raise HTTPException(404, f"{name} not found for run {run_id}")
    return FileResponse(
        target,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/{run_id}/download")
def download_run_zip(
    sid: str, run_id: str, store: SessionStore = Depends(get_store)
):
    if not store.exists(sid):
        raise HTTPException(404, "session not found")
    runs_dir = store.get(sid).runs_dir
    run_dir = (runs_dir / run_id).resolve()
    if not run_dir.is_relative_to(runs_dir.resolve()):
        raise HTTPException(400, "invalid run_id")
    if not run_dir.exists():
        raise HTTPException(404, "run not found")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in run_dir.rglob("*"):
            if p.is_file():
                zf.write(p, arcname=p.relative_to(run_dir))
    buf.seek(0)
    zip_name = f"{run_id}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )


def _write_status(path, data: dict) -> None:
    try:
        path.write_text(json.dumps(data, default=str, ensure_ascii=False))
    except Exception:
        pass
