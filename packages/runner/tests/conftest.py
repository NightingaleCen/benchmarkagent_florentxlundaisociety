import textwrap
from pathlib import Path

import pytest


@pytest.fixture
def tmp_artifact(tmp_path: Path) -> Path:
    """Build a minimal valid artifact directory in a tmp path."""
    root = tmp_path / "art"
    root.mkdir()
    (root / "manifest.yaml").write_text(
        textwrap.dedent("""
        schema_version: "0.1"
        name: tmp-demo
        description: tmp demo
        task:
          type: binary_classification
          input_schema:
            text: { type: string }
          output_schema:
            label: { type: string, enum: ["yes", "no"] }
        evaluator:
          judge:
            type: rule
        dataset:
          path: dataset.jsonl
          count: 2
        """)
    )
    (root / "dataset.jsonl").write_text(
        '{"input": {"text": "hello"}, "expected": {"label": "yes"}}\n'
        '{"input": {"text": "bye"}, "expected": {"label": "no"}}\n'
    )
    (root / "adapter.py").write_text(
        textwrap.dedent("""
        def run_model(model_client, input_record):
            resp = model_client.complete(prompt=input_record["text"])
            return {
                "output": {"label": resp.text.strip()},
                "usage": {"input_tokens": resp.input_tokens, "output_tokens": resp.output_tokens},
                "latency_ms": 1,
                "raw_response": None,
            }
        """)
    )
    (root / "evaluator.py").write_text(
        textwrap.dedent("""
        def evaluate(model_output, expected, judge=None):
            s = 1 if model_output.get("label") == expected.get("label") else 0
            return {"score": s, "reason": f"{model_output} vs {expected}"}
        """)
    )
    return root
