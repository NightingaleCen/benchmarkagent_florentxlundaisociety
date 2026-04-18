from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    sessions_root: Path
    orchestrator_model: str
    max_agent_iterations: int

    @classmethod
    def from_env(cls) -> "Settings":
        default_sessions = str(Path.home() / ".benchmarkagent" / "sessions")
        root = Path(os.environ.get("BMK_SESSIONS_ROOT", default_sessions)).resolve()
        return cls(
            sessions_root=root,
            orchestrator_model=os.environ.get(
                "BMK_ORCHESTRATOR_MODEL", "claude-sonnet-4-6"
            ),
            max_agent_iterations=int(os.environ.get("BMK_MAX_AGENT_ITERATIONS", "40")),
        )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings
