"""Judge wrappers. The evaluator calls ``judge.score(**fields)`` when the
manifest declares an LLM judge. The runner passes ``None`` for rule judges.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from artifact_schema import LLMJudgeSpec

from benchmarkrun.model_clients import build_model_client


@dataclass
class JudgeVerdict:
    pass_: bool
    explanation: str
    prompt: str
    raw: Any
    model: str


class LLMJudge:
    def __init__(self, spec: LLMJudgeSpec) -> None:
        self.spec = spec
        self.model = spec.model
        # Supports `provider:model` syntax inside spec.model, same as the CLI.
        self._client = build_model_client(spec.model)

    def score(self, **fields: Any) -> JudgeVerdict:
        prompt = self.spec.prompt_template.format(**fields)
        response = self._client.messages(
            [{"role": "user", "content": prompt}],
            temperature=self.spec.temperature,
            max_tokens=256,
        )
        verdict_text = response.text.strip().lower()
        passed = verdict_text.startswith("yes") or verdict_text.startswith("pass") or (
            "yes" in verdict_text.split()[:3]
        )
        return JudgeVerdict(
            pass_=passed,
            explanation=response.text.strip(),
            prompt=prompt,
            raw=response.raw,
            model=self.spec.model,
        )


def build_judge(spec) -> LLMJudge | None:
    """Return an LLMJudge if the spec calls for one, else None (rule path)."""
    if isinstance(spec, LLMJudgeSpec):
        return LLMJudge(spec)
    return None
