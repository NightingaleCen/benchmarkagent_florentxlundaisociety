"""Load an artifact directory: validate manifest, import adapter + evaluator,
validate runtime requirements."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

from artifact_schema import Manifest, load_manifest

_SPEC_SPLIT = re.compile(r"[\s<>=!~]")


@dataclass
class LoadedArtifact:
    root: Path
    manifest: Manifest
    adapter_fn: Callable[..., dict]
    evaluator_fn: Callable[..., dict]


def _import_file(path: Path, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    # Register so dataclasses/pydantic that rely on __module__ can resolve
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _resolve_entrypoint(module: ModuleType, name: str, source: Path) -> Callable[..., Any]:
    fn = getattr(module, name, None)
    if fn is None:
        raise RuntimeError(f"{source}: missing entrypoint {name!r}")
    if not callable(fn):
        raise RuntimeError(f"{source}: entrypoint {name!r} is not callable")
    return fn


def _dist_name(spec: str) -> str:
    """Extract distribution name from a spec like 'tiktoken>=0.5' or 'requests'."""
    parts = _SPEC_SPLIT.split(spec.strip(), maxsplit=1)
    return parts[0]


def check_requirements(requirements: list[str]) -> list[str]:
    """Return a list of human-readable errors for missing requirements.
    Empty list = all present."""
    errors: list[str] = []
    for req in requirements:
        name = _dist_name(req)
        if not name:
            continue
        try:
            importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            errors.append(f"missing required package: {req!r} (pip install '{req}')")
    return errors


def load_artifact(root: str | Path) -> LoadedArtifact:
    root = Path(root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"{root}: not a directory")

    manifest_path = root / "manifest.yaml"
    if not manifest_path.exists():
        raise FileNotFoundError(f"{manifest_path}: not found")

    manifest = load_manifest(manifest_path)

    req_errors = check_requirements(manifest.runtime.requirements)
    if req_errors:
        raise RuntimeError(
            "runtime requirements not satisfied:\n  " + "\n  ".join(req_errors)
        )

    adapter_path = root / manifest.adapter.module
    evaluator_path = root / manifest.evaluator.module
    if not adapter_path.exists():
        raise FileNotFoundError(f"{adapter_path}: not found")
    if not evaluator_path.exists():
        raise FileNotFoundError(f"{evaluator_path}: not found")

    adapter_mod = _import_file(adapter_path, f"_bmk_adapter_{id(manifest)}")
    evaluator_mod = _import_file(evaluator_path, f"_bmk_evaluator_{id(manifest)}")

    adapter_fn = _resolve_entrypoint(
        adapter_mod, manifest.adapter.entrypoint, adapter_path
    )
    evaluator_fn = _resolve_entrypoint(
        evaluator_mod, manifest.evaluator.entrypoint, evaluator_path
    )

    return LoadedArtifact(
        root=root,
        manifest=manifest,
        adapter_fn=adapter_fn,
        evaluator_fn=evaluator_fn,
    )
