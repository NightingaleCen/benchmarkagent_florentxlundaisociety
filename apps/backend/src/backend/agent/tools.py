"""Tools exposed to the orchestrator agent.

Each tool has an Anthropic tool schema and an implementation bound to a
Session instance. The tool loop dispatches tool_use blocks to these.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from benchmarkrun.loader import load_artifact
from benchmarkrun.runtime import run_benchmark

from backend.sessions import Session


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict], str]


def _ok(payload: Any) -> str:
    return json.dumps({"ok": True, "result": payload}, ensure_ascii=False, default=str)


def _err(message: str) -> str:
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False)


def _is_data_path(path: str) -> bool:
    normalized = Path(path).as_posix().lstrip("./")
    return normalized == "dataset.jsonl" or normalized.startswith("data/")


def build_tools(
    session: Session, *, allow_agent_data_access: bool = True
) -> list[ToolSpec]:
    def read_artifact_file(args: dict) -> str:
        path = args["path"]
        if not allow_agent_data_access and _is_data_path(path):
            return _err("agent data access is disabled for dataset files")
        try:
            return _ok({"path": path, "content": session.read_artifact_file(path)})
        except FileNotFoundError:
            return _err(f"file not found: {path}")
        except Exception as e:
            return _err(str(e))

    def write_artifact_file(args: dict) -> str:
        path = args["path"]
        content = args["content"]
        if not allow_agent_data_access and _is_data_path(path):
            return _err("agent data access is disabled for dataset files")
        try:
            session.write_artifact_file(path, content)
            return _ok({"path": path, "bytes": len(content.encode("utf-8"))})
        except Exception as e:
            return _err(str(e))

    def list_artifact_files(args: dict) -> str:
        return _ok({"files": session.list_artifact_files()})

    def dry_run(args: dict) -> str:
        if not allow_agent_data_access:
            return _err("dry_run is unavailable while agent data access is disabled")
        sample_size = int(args.get("sample_size", 3))
        model_id = args.get("model", "claude-haiku-4-5-20251001")
        provider = args.get("provider")
        out_dir = session.runs_dir / "dry_run"
        try:
            artifact = load_artifact(session.artifact_dir)
        except Exception as e:
            return _err(f"artifact failed to load: {e}")
        try:
            summary = run_benchmark(
                artifact,
                model_id=model_id,
                out_dir=out_dir,
                limit=sample_size,
                provider=provider,
            )
        except Exception as e:
            return _err(f"dry run failed: {e}")
        return _ok(
            {
                "count": summary.count,
                "passed": summary.passed,
                "failed": summary.failed,
                "errored": summary.errored,
                "pass_rate": summary.pass_rate,
                "sample": _read_first_results(out_dir / "results.jsonl", 3),
            }
        )

    return [
        ToolSpec(
            name="read_artifact_file",
            description=(
                "Read the current contents of a file in the session's artifact workspace. "
                "Use this before editing so you edit against the real current state."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "path relative to the artifact dir (e.g. 'manifest.yaml')",
                    }
                },
                "required": ["path"],
            },
            handler=read_artifact_file,
        ),
        ToolSpec(
            name="write_artifact_file",
            description=(
                "Write (or overwrite) a file in the artifact workspace. This is how you commit "
                "any artifact change — never describe a change, write it."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
            handler=write_artifact_file,
        ),
        ToolSpec(
            name="list_artifact_files",
            description="List all files currently in the artifact workspace.",
            input_schema={"type": "object", "properties": {}},
            handler=list_artifact_files,
        ),
        ToolSpec(
            name="dry_run",
            description=(
                "Run the benchmarkrun CLI on a small sample of the artifact to verify it works "
                "end-to-end. Returns pass/fail counts and a sample of results. Use this after "
                "writing all four artifact files and before handing off to the user."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "sample_size": {
                        "type": "integer",
                        "description": "how many dataset records to run",
                        "default": 3,
                    },
                    "model": {
                        "type": "string",
                        "description": (
                            "model id to test with; defaults to a cheap haiku model. "
                            "Supports `provider:model` syntax (e.g. `openai:gpt-4o-mini`)."
                        ),
                    },
                    "provider": {
                        "type": "string",
                        "enum": ["anthropic", "openai"],
                        "description": "explicit provider override; see --provider",
                    },
                },
            },
            handler=dry_run,
        ),
    ]


def _read_first_results(path: Path, n: int) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= n:
                break
            out.append(json.loads(line))
    return out


def tools_to_anthropic_format(tools: list[ToolSpec]) -> list[dict]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_schema,
        }
        for t in tools
    ]
