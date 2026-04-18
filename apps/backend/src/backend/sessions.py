"""Session workspace management.

A session is a directory under `sessions_root/{id}/`:

    sessions/{id}/
        artifact/        # live, editable artifact (manifest.yaml, etc.)
        chat.jsonl       # append-only conversation log
        runs/            # output directories from benchmark runs

The filesystem IS the persistence layer. No database in MVP.
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

_SAFE_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-/")


def _safe_relpath(rel: str) -> Path:
    """Reject escape attempts (absolute, .., control chars) and return a relative Path."""
    if not rel or rel.startswith("/"):
        raise ValueError(f"invalid path: {rel!r}")
    for ch in rel:
        if ch not in _SAFE_CHARS:
            raise ValueError(f"invalid character in path: {rel!r}")
    p = Path(rel)
    if any(part == ".." for part in p.parts):
        raise ValueError(f"path escape detected: {rel!r}")
    return p


@dataclass
class Session:
    id: str
    root: Path

    @property
    def artifact_dir(self) -> Path:
        return self.root / "artifact"

    @property
    def chat_log(self) -> Path:
        return self.root / "chat.jsonl"

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"

    def read_artifact_file(self, rel: str) -> str:
        p = self.artifact_dir / _safe_relpath(rel)
        if not p.exists():
            raise FileNotFoundError(rel)
        return p.read_text(encoding="utf-8")

    def write_artifact_file(self, rel: str, content: str) -> Path:
        p = self.artifact_dir / _safe_relpath(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def list_artifact_files(self) -> list[str]:
        if not self.artifact_dir.exists():
            return []
        return sorted(
            str(p.relative_to(self.artifact_dir))
            for p in self.artifact_dir.rglob("*")
            if p.is_file()
        )

    def append_chat(self, entry: dict[str, Any]) -> None:
        entry = {"ts": datetime.now(timezone.utc).isoformat(), **entry}
        with self.chat_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def iter_chat(self) -> Iterator[dict[str, Any]]:
        if not self.chat_log.exists():
            return iter(())
        with self.chat_log.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)


class SessionStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self) -> Session:
        sid = uuid.uuid4().hex[:12]
        session_root = self.root / sid
        session_root.mkdir()
        (session_root / "artifact").mkdir()
        (session_root / "runs").mkdir()
        return Session(id=sid, root=session_root)

    def get(self, sid: str) -> Session:
        p = self.root / sid
        if not p.is_dir():
            raise KeyError(sid)
        return Session(id=sid, root=p)

    def exists(self, sid: str) -> bool:
        return (self.root / sid).is_dir()

    def list_ids(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir() if p.is_dir())

    def delete(self, sid: str) -> None:
        p = self.root / sid
        if p.is_dir():
            shutil.rmtree(p)
