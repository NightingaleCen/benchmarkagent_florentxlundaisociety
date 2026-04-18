from pathlib import Path

import pytest

from artifact_schema import DatasetRecord, iter_dataset


def test_valid_dataset_parses(tmp_path: Path):
    path = tmp_path / "dataset.jsonl"
    path.write_text(
        '{"input": {"text": "a"}, "expected": {"label": "yes"}}\n'
        '{"input": {"text": "b"}, "expected": {"label": "no"}}\n'
    )
    records = list(iter_dataset(path))
    assert len(records) == 2
    assert records[0].input == {"text": "a"}
    assert records[1].expected == {"label": "no"}


def test_blank_lines_skipped(tmp_path: Path):
    path = tmp_path / "dataset.jsonl"
    path.write_text(
        '{"input": {"text": "a"}, "expected": {"label": "yes"}}\n'
        "\n"
        '{"input": {"text": "b"}, "expected": {"label": "no"}}\n'
    )
    records = list(iter_dataset(path))
    assert len(records) == 2


def test_malformed_json_reports_line(tmp_path: Path):
    path = tmp_path / "dataset.jsonl"
    path.write_text(
        '{"input": {"text": "a"}, "expected": {"label": "yes"}}\n'
        "not-json\n"
    )
    with pytest.raises(ValueError, match=":2:"):
        list(iter_dataset(path))


def test_missing_required_field_reports_line(tmp_path: Path):
    path = tmp_path / "dataset.jsonl"
    path.write_text('{"input": {"text": "a"}}\n')
    with pytest.raises(ValueError, match=":1:"):
        list(iter_dataset(path))


def test_extra_field_rejected(tmp_path: Path):
    path = tmp_path / "dataset.jsonl"
    path.write_text(
        '{"input": {"text": "a"}, "expected": {"label": "yes"}, "comment": "oops"}\n'
    )
    with pytest.raises(ValueError):
        list(iter_dataset(path))


def test_record_model_direct():
    r = DatasetRecord(input={"x": 1}, expected={"y": 2})
    assert r.input["x"] == 1
