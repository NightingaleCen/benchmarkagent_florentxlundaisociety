"""Main benchmark execution loop."""

from __future__ import annotations

import traceback
from collections.abc import Iterator
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from artifact_schema import LLMJudgeSpec, iter_dataset

from benchmarkrun import __version__
from benchmarkrun.judges import build_judge
from benchmarkrun.loader import LoadedArtifact
from benchmarkrun.model_clients import build_model_client
from benchmarkrun.reporting import ResultsWriter, SampleResult, Summary

def _build_summary(
    artifact: LoadedArtifact,
    model_id: str,
    passed: int,
    failed: int,
    errored: int,
    total_in_tokens: int,
    total_out_tokens: int,
    total_latency_ms: int,
    latency_samples: int,
    started_at: str,
    writer: ResultsWriter,
) -> Summary:
    finished_at = datetime.now(timezone.utc).isoformat()
    total_scored = passed + failed
    pass_rate = passed / total_scored if total_scored else 0.0
    mean_latency = total_latency_ms / latency_samples if latency_samples else 0.0

    judge_spec = artifact.manifest.evaluator.judge
    if isinstance(judge_spec, LLMJudgeSpec):
        judge_config: dict = {
            "type": "llm",
            "model": judge_spec.model,
            "temperature": judge_spec.temperature,
            "prompt_template": judge_spec.prompt_template,
        }
    else:
        judge_config = {"type": "rule"}

    summary = Summary(
        artifact_name=artifact.manifest.name,
        model=model_id,
        judge_config=judge_config,
        count=passed + failed + errored,
        passed=passed,
        failed=failed,
        errored=errored,
        pass_rate=pass_rate,
        total_input_tokens=total_in_tokens,
        total_output_tokens=total_out_tokens,
        mean_latency_ms=mean_latency,
        runner_version=__version__,
        started_at=started_at,
        finished_at=finished_at,
        schema_version=artifact.manifest.schema_version,
    )
    writer.write_summary(summary)
    return summary


def run_benchmark_iter(
    artifact: LoadedArtifact,
    *,
    model_id: str,
    out_dir: Path,
    limit: int | None = None,
    provider: str | None = None,
) -> Iterator[dict]:
    """Generator version of run_benchmark that yields progress events per sample.

    Yields:
      {"event": "started",  "total": N, "model": str}
      {"event": "sample",   "index": N, "done": N, "total": N, "score": int|None,
                             "reason": str|None, "error": str|None,
                             "passed": N, "failed": N, "errored": N, "latency_ms": int|None}
      {"event": "done",     "run_id": str, "summary": dict}
    """
    manifest = artifact.manifest
    dataset_path = artifact.root / manifest.dataset.path

    # Pre-count for accurate progress display.
    with open(dataset_path) as f:
        total_in_file = sum(1 for line in f if line.strip())
    total = min(total_in_file, limit) if limit is not None else total_in_file

    model_client = build_model_client(model_id, provider=provider)
    judge = build_judge(manifest.evaluator.judge)

    writer = ResultsWriter(out_dir)
    passed = failed = errored = 0
    total_in_tokens = total_out_tokens = 0
    total_latency_ms = 0
    latency_samples = 0
    started_at = datetime.now(timezone.utc).isoformat()

    yield {"event": "started", "total": total, "model": model_id}

    try:
        for index, record in enumerate(iter_dataset(dataset_path)):
            if limit is not None and index >= limit:
                break

            sample_error: str | None = None
            model_output = None
            score = None
            reason = None
            usage = None
            latency_ms = None
            judge_trace = None
            raw_response = None

            try:
                adapter_result = artifact.adapter_fn(model_client, record.input)
                model_output = adapter_result.get("output")
                usage = adapter_result.get("usage")
                latency_ms = adapter_result.get("latency_ms")
                raw_response = adapter_result.get("raw_response")

                eval_result = artifact.evaluator_fn(model_output, record.expected, judge)
                score = int(eval_result.get("score", 0))
                reason = eval_result.get("reason", "")
                judge_trace = eval_result.get("judge_trace")

                if score == 1:
                    passed += 1
                else:
                    failed += 1

                if usage:
                    total_in_tokens += int(usage.get("input_tokens", 0) or 0)
                    total_out_tokens += int(usage.get("output_tokens", 0) or 0)
                if latency_ms is not None:
                    total_latency_ms += int(latency_ms)
                    latency_samples += 1

            except Exception:
                errored += 1
                sample_error = traceback.format_exc()

            writer.write(
                SampleResult(
                    index=index,
                    input=record.input,
                    expected=record.expected,
                    model_output=model_output,
                    score=score,
                    reason=reason,
                    error=sample_error,
                    usage=usage,
                    latency_ms=latency_ms,
                    judge_trace=judge_trace,
                    raw_response=raw_response,
                )
            )

            reason_preview = reason[:120] if reason else None
            error_preview = sample_error.splitlines()[0] if sample_error else None
            yield {
                "event": "sample",
                "index": index,
                "done": index + 1,
                "total": total,
                "score": score,
                "reason": reason_preview,
                "error": error_preview,
                "passed": passed,
                "failed": failed,
                "errored": errored,
                "latency_ms": latency_ms,
            }
    finally:
        writer.close()

    summary = _build_summary(
        artifact,
        model_id,
        passed,
        failed,
        errored,
        total_in_tokens,
        total_out_tokens,
        total_latency_ms,
        latency_samples,
        started_at,
        writer,
    )
    yield {"event": "done", "run_id": out_dir.name, "summary": asdict(summary)}


def run_benchmark(
    artifact: LoadedArtifact,
    *,
    model_id: str,
    out_dir: Path,
    limit: int | None = None,
    provider: str | None = None,
) -> Summary:
    """Synchronous wrapper — runs all samples and returns the final Summary."""
    for event in run_benchmark_iter(
        artifact,
        model_id=model_id,
        out_dir=out_dir,
        limit=limit,
        provider=provider,
    ):
        if event["event"] == "done":
            s = event["summary"]
            return Summary(**{k: s[k] for k in s if k in {f.name for f in __import__("dataclasses").fields(Summary)}})
    raise RuntimeError("run_benchmark_iter exhausted without a 'done' event")
