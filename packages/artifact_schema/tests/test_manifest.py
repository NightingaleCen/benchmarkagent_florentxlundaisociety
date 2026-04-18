import textwrap
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from artifact_schema import SCHEMA_VERSION, LLMJudgeSpec, Manifest, load_manifest


def _valid_raw() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "name": "demo",
        "description": "a demo",
        "task": {
            "type": "binary_classification",
            "input_schema": {"text": {"type": "string"}},
            "output_schema": {
                "label": {"type": "string", "enum": ["yes", "no"]},
            },
        },
        "evaluator": {"judge": {"type": "rule"}},
        "dataset": {"count": 5},
    }


def test_valid_rule_manifest_parses():
    m = Manifest.model_validate(_valid_raw())
    assert m.name == "demo"
    assert m.evaluator.judge.type == "rule"
    assert m.adapter.entrypoint == "run_model"
    assert m.runtime.requirements == []


def test_valid_llm_judge_manifest_parses():
    raw = _valid_raw()
    raw["evaluator"]["judge"] = {
        "type": "llm",
        "model": "claude-sonnet-4-6",
        "temperature": 0,
        "prompt_template": "Score: {answer}",
    }
    m = Manifest.model_validate(raw)
    assert isinstance(m.evaluator.judge, LLMJudgeSpec)
    assert m.evaluator.judge.temperature == 0


def test_rejects_unknown_schema_version():
    raw = _valid_raw()
    raw["schema_version"] = "99.0"
    with pytest.raises(ValidationError, match="schema_version"):
        Manifest.model_validate(raw)


def test_rejects_missing_schema_version():
    raw = _valid_raw()
    del raw["schema_version"]
    with pytest.raises(ValidationError):
        Manifest.model_validate(raw)


def test_rejects_llm_judge_missing_model():
    raw = _valid_raw()
    raw["evaluator"]["judge"] = {
        "type": "llm",
        "temperature": 0,
        "prompt_template": "x",
    }
    with pytest.raises(ValidationError, match="model"):
        Manifest.model_validate(raw)


def test_rejects_llm_judge_missing_temperature():
    raw = _valid_raw()
    raw["evaluator"]["judge"] = {
        "type": "llm",
        "model": "claude-sonnet-4-6",
        "prompt_template": "x",
    }
    with pytest.raises(ValidationError, match="temperature"):
        Manifest.model_validate(raw)


def test_rejects_llm_judge_missing_prompt_template():
    raw = _valid_raw()
    raw["evaluator"]["judge"] = {
        "type": "llm",
        "model": "claude-sonnet-4-6",
        "temperature": 0,
    }
    with pytest.raises(ValidationError, match="prompt_template"):
        Manifest.model_validate(raw)


def test_rejects_empty_input_schema():
    raw = _valid_raw()
    raw["task"]["input_schema"] = {}
    with pytest.raises(ValidationError, match="at least one field"):
        Manifest.model_validate(raw)


def test_rejects_unknown_task_type():
    raw = _valid_raw()
    raw["task"]["type"] = "generation"
    with pytest.raises(ValidationError):
        Manifest.model_validate(raw)


def test_rejects_extra_fields_at_root():
    raw = _valid_raw()
    raw["mystery_field"] = 1
    with pytest.raises(ValidationError):
        Manifest.model_validate(raw)


def test_load_manifest_from_yaml(tmp_path: Path):
    path = tmp_path / "manifest.yaml"
    path.write_text(
        textwrap.dedent(f"""
        schema_version: "{SCHEMA_VERSION}"
        name: contracts
        description: clause classifier
        task:
          type: binary_classification
          input_schema:
            clause_text: {{ type: string }}
          output_schema:
            label: {{ type: string, enum: ["indemnification", "other"] }}
        evaluator:
          judge:
            type: rule
        dataset:
          count: 3
        runtime:
          python: ">=3.11"
          requirements: ["tiktoken>=0.5"]
        """)
    )
    m = load_manifest(path)
    assert m.name == "contracts"
    assert m.runtime.requirements == ["tiktoken>=0.5"]


def test_load_manifest_rejects_non_mapping(tmp_path: Path):
    path = tmp_path / "manifest.yaml"
    path.write_text("- just a list")
    with pytest.raises(ValueError, match="must be a mapping"):
        load_manifest(path)


def test_load_manifest_round_trip(tmp_path: Path):
    raw = _valid_raw()
    path = tmp_path / "manifest.yaml"
    path.write_text(yaml.safe_dump(raw))
    m = load_manifest(path)
    assert m.name == "demo"
