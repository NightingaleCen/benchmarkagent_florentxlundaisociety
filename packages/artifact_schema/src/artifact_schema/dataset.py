import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


class DatasetRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: dict[str, Any]
    expected: dict[str, Any]


def iter_dataset(path: str | Path) -> Iterator[DatasetRecord]:
    """Stream-parse a dataset.jsonl file, one DatasetRecord per line.

    Raises ValueError with line number on malformed rows.
    """
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                raw = json.loads(stripped)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {e}") from e
            try:
                yield DatasetRecord.model_validate(raw)
            except Exception as e:
                raise ValueError(f"{path}:{lineno}: invalid record: {e}") from e
