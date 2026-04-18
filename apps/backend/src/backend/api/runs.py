from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from benchmarkrun.loader import load_artifact
from benchmarkrun.runtime import run_benchmark

from backend.api.sessions import get_store
from backend.sessions import SessionStore

router = APIRouter(prefix="/sessions/{sid}/runs", tags=["runs"])


class RunRequest(BaseModel):
    model: str
    limit: int | None = None


@router.post("")
def trigger_run(
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
    try:
        summary = run_benchmark(
            artifact, model_id=body.model, out_dir=out_dir, limit=body.limit
        )
    except Exception as e:
        raise HTTPException(500, f"run failed: {e}")

    return {
        "run_id": stamp,
        "summary": _summary_to_dict(summary),
    }


@router.get("")
def list_runs(sid: str, store: SessionStore = Depends(get_store)):
    if not store.exists(sid):
        raise HTTPException(404, "session not found")
    session = store.get(sid)
    runs: list[dict] = []
    if session.runs_dir.exists():
        for run_dir in sorted(session.runs_dir.iterdir()):
            summary_file = run_dir / "summary.json"
            if summary_file.exists():
                runs.append({"run_id": run_dir.name, "summary": json.loads(summary_file.read_text())})
    return {"runs": runs}


@router.get("/{run_id}")
def get_run(sid: str, run_id: str, store: SessionStore = Depends(get_store)):
    if not store.exists(sid):
        raise HTTPException(404, "session not found")
    run_dir = store.get(sid).runs_dir / run_id
    summary_file = run_dir / "summary.json"
    results_file = run_dir / "results.jsonl"
    if not summary_file.exists():
        raise HTTPException(404, "run not found")
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


def _summary_to_dict(summary) -> dict:
    from dataclasses import asdict

    return asdict(summary)
