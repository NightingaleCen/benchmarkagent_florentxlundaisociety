"""benchmarkrun CLI entrypoint."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from benchmarkrun import __version__
from benchmarkrun.loader import load_artifact
from benchmarkrun.runtime import run_benchmark


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="benchmarkrun",
        description="Execute a BenchmarkAgent artifact against an LLM.",
    )
    p.add_argument("artifact_dir", type=Path, help="path to the artifact directory")
    p.add_argument(
        "--model",
        required=True,
        help="model id (e.g. claude-sonnet-4-6, gpt-4o-mini)",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="only run the first N dataset samples",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output directory (default: <artifact_dir>/runs/<timestamp>)",
    )
    p.add_argument("--version", action="version", version=f"benchmarkrun {__version__}")
    return p


def _default_out(artifact_dir: Path) -> Path:
    from datetime import datetime, timezone

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return artifact_dir / "runs" / stamp


def main(argv: list[str] | None = None) -> int:
    from dotenv import load_dotenv

    load_dotenv()

    args = build_parser().parse_args(argv)
    try:
        artifact = load_artifact(args.artifact_dir)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    out_dir = args.out if args.out is not None else _default_out(artifact.root)
    print(f"artifact: {artifact.manifest.name} (schema v{artifact.manifest.schema_version})")
    print(f"model:    {args.model}")
    print(f"out:      {out_dir}")

    try:
        summary = run_benchmark(
            artifact,
            model_id=args.model,
            out_dir=out_dir,
            limit=args.limit,
        )
    except Exception as e:
        print(f"run failed: {e}", file=sys.stderr)
        return 1

    print(
        f"\ndone: {summary.passed}/{summary.count} passed "
        f"(rate={summary.pass_rate:.3f}, errored={summary.errored})"
    )
    print(f"tokens: in={summary.total_input_tokens}, out={summary.total_output_tokens}")
    print(f"mean latency: {summary.mean_latency_ms:.0f}ms")
    print(f"results: {out_dir}/results.jsonl")
    print(f"summary: {out_dir}/summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
