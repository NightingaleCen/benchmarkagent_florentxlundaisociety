import json
import textwrap
from dataclasses import dataclass
from pathlib import Path

import pytest

from benchmarkrun.loader import load_artifact
from benchmarkrun.model_clients import CompletionResponse
from benchmarkrun.runtime import run_benchmark


@dataclass
class _FakeClient:
    """A ModelClient stub. The adapter passes input_record['text'] as the prompt,
    and this stub echoes that prompt back mapped through a table."""

    table: dict[str, str]
    model_id: str = "fake-model"
    raw_client: object = None

    def complete(self, prompt: str, **kwargs) -> CompletionResponse:
        return CompletionResponse(
            text=self.table.get(prompt, "?"),
            input_tokens=len(prompt),
            output_tokens=1,
            raw={"prompt": prompt},
        )

    def messages(self, messages, **kwargs) -> CompletionResponse:
        raise NotImplementedError


@pytest.fixture
def patched_build(monkeypatch):
    def _install(table):
        def fake_build(model_id: str):
            return _FakeClient(table=table, model_id=model_id)

        import benchmarkrun.runtime as rt

        monkeypatch.setattr(rt, "build_model_client", fake_build)

    return _install


def test_full_run_all_pass(tmp_artifact: Path, patched_build, tmp_path: Path):
    patched_build({"hello": "yes", "bye": "no"})
    art = load_artifact(tmp_artifact)
    out = tmp_path / "out"
    summary = run_benchmark(art, model_id="fake", out_dir=out, limit=None)

    assert summary.count == 2
    assert summary.passed == 2
    assert summary.failed == 0
    assert summary.errored == 0
    assert summary.pass_rate == 1.0

    results = [
        json.loads(line)
        for line in (out / "results.jsonl").read_text().splitlines()
    ]
    assert [r["score"] for r in results] == [1, 1]

    summary_file = json.loads((out / "summary.json").read_text())
    assert summary_file["artifact_name"] == "tmp-demo"
    assert summary_file["judge_config"] == {"type": "rule"}


def test_partial_fail(tmp_artifact: Path, patched_build, tmp_path: Path):
    patched_build({"hello": "yes", "bye": "yes"})
    art = load_artifact(tmp_artifact)
    summary = run_benchmark(
        art, model_id="fake", out_dir=tmp_path / "out", limit=None
    )
    assert summary.passed == 1
    assert summary.failed == 1
    assert summary.pass_rate == 0.5


def test_adapter_exception_recorded_not_raised(
    tmp_artifact: Path, patched_build, tmp_path: Path
):
    # adapter raises for the second input
    (tmp_artifact / "adapter.py").write_text(
        textwrap.dedent("""
        def run_model(model_client, input_record):
            if input_record["text"] == "bye":
                raise RuntimeError("boom")
            resp = model_client.complete(prompt=input_record["text"])
            return {
                "output": {"label": resp.text.strip()},
                "usage": {"input_tokens": resp.input_tokens, "output_tokens": resp.output_tokens},
                "latency_ms": 1,
                "raw_response": None,
            }
        """)
    )

    patched_build({"hello": "yes", "bye": "no"})
    art = load_artifact(tmp_artifact)
    out = tmp_path / "out"
    summary = run_benchmark(art, model_id="fake", out_dir=out, limit=None)

    assert summary.passed == 1
    assert summary.failed == 0
    assert summary.errored == 1
    assert summary.count == 2

    lines = [
        json.loads(line)
        for line in (out / "results.jsonl").read_text().splitlines()
    ]
    assert lines[0]["error"] is None
    assert "boom" in lines[1]["error"]


def test_limit_truncates(tmp_artifact: Path, patched_build, tmp_path: Path):
    patched_build({"hello": "yes", "bye": "no"})
    art = load_artifact(tmp_artifact)
    summary = run_benchmark(
        art, model_id="fake", out_dir=tmp_path / "out", limit=1
    )
    assert summary.count == 1
    assert summary.passed == 1
