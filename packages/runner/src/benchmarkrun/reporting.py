"""Write results.jsonl and summary.json to the output directory."""

from __future__ import annotations

import dataclasses
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SampleResult:
    index: int
    input: dict
    expected: dict
    model_output: dict | None
    score: int | None
    reason: str | None
    error: str | None
    usage: dict | None
    latency_ms: int | None
    judge_trace: dict | None
    raw_response: Any | None = None


@dataclass
class Summary:
    artifact_name: str
    model: str
    judge_config: dict
    count: int
    passed: int
    failed: int
    errored: int
    pass_rate: float
    total_input_tokens: int
    total_output_tokens: int
    mean_latency_ms: float
    runner_version: str
    started_at: str
    finished_at: str
    schema_version: str
    extras: dict = field(default_factory=dict)


class ResultsWriter:
    """Open an append-only results.jsonl writer for a run."""

    def __init__(self, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        self.out_dir = out_dir
        self._results_path = out_dir / "results.jsonl"
        self._fp = self._results_path.open("w", encoding="utf-8")

    def write(self, sample: SampleResult) -> None:
        self._fp.write(json.dumps(asdict(sample), default=_json_default) + "\n")
        self._fp.flush()

    def close(self) -> None:
        self._fp.close()

    def write_summary(self, summary: Summary) -> Path:
        path = self.out_dir / "summary.json"
        path.write_text(
            json.dumps(asdict(summary), indent=2, default=_json_default) + "\n",
            encoding="utf-8",
        )
        return path


def _json_default(o: Any) -> Any:
    if hasattr(o, "model_dump"):
        return o.model_dump()
    if hasattr(o, "to_dict"):
        return o.to_dict()
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return dataclasses.asdict(o)
    if hasattr(o, "__dict__"):
        return o.__dict__
    return repr(o)
