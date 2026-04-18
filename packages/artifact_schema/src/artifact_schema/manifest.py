from pathlib import Path
from typing import Annotated, Literal, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "0.1"


class FieldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["string", "number", "integer", "boolean"]
    enum: list[str] | None = None
    description: str | None = None


class TaskSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["binary_classification"]
    input_schema: dict[str, FieldSpec]
    output_schema: dict[str, FieldSpec]

    @field_validator("input_schema", "output_schema")
    @classmethod
    def _non_empty(cls, v: dict[str, FieldSpec]) -> dict[str, FieldSpec]:
        if not v:
            raise ValueError("schema must declare at least one field")
        return v


class AdapterSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module: str = "adapter.py"
    entrypoint: str = "run_model"


class RuleJudgeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["rule"]


class LLMJudgeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["llm"]
    model: str
    temperature: float
    prompt_template: str

    @field_validator("prompt_template")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("prompt_template must not be empty")
        return v


JudgeSpec = Annotated[
    Union[RuleJudgeSpec, LLMJudgeSpec],
    Field(discriminator="type"),
]


class EvaluatorSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module: str = "evaluator.py"
    entrypoint: str = "evaluate"
    judge: JudgeSpec


class DatasetSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = "dataset.jsonl"
    count: int = Field(ge=1)


class RuntimeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    python: str = ">=3.11"
    requirements: list[str] = Field(default_factory=list)


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    name: str
    description: str
    created_by: str | None = None
    created_at: str | None = None
    task: TaskSpec
    adapter: AdapterSpec = Field(default_factory=AdapterSpec)
    evaluator: EvaluatorSpec
    dataset: DatasetSpec
    runtime: RuntimeSpec = Field(default_factory=RuntimeSpec)

    @model_validator(mode="after")
    def _check_schema_version(self) -> "Manifest":
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported schema_version: {self.schema_version!r}. "
                f"this runner supports {SCHEMA_VERSION!r}."
            )
        return self

    @field_validator("name")
    @classmethod
    def _valid_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty")
        return v


def load_manifest(path: str | Path) -> Manifest:
    """Load and validate a manifest.yaml file."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: manifest root must be a mapping")
    return Manifest.model_validate(raw)
