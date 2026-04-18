from pathlib import Path

import pytest

from benchmarkrun.loader import check_requirements, load_artifact


def test_load_artifact_resolves_entrypoints(tmp_artifact: Path):
    art = load_artifact(tmp_artifact)
    assert art.manifest.name == "tmp-demo"
    assert callable(art.adapter_fn)
    assert callable(art.evaluator_fn)


def test_load_artifact_missing_dir(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_artifact(tmp_path / "nope")


def test_load_artifact_missing_manifest(tmp_path: Path):
    d = tmp_path / "empty"
    d.mkdir()
    with pytest.raises(FileNotFoundError, match="manifest.yaml"):
        load_artifact(d)


def test_load_artifact_missing_adapter(tmp_artifact: Path):
    (tmp_artifact / "adapter.py").unlink()
    with pytest.raises(FileNotFoundError, match="adapter.py"):
        load_artifact(tmp_artifact)


def test_load_artifact_entrypoint_missing(tmp_artifact: Path):
    (tmp_artifact / "adapter.py").write_text("# no entrypoint here\n")
    with pytest.raises(RuntimeError, match="run_model"):
        load_artifact(tmp_artifact)


def test_check_requirements_all_present():
    # pydantic is a hard dep, always present
    assert check_requirements(["pydantic>=2.0"]) == []


def test_check_requirements_missing():
    errs = check_requirements(["definitely-not-a-real-package-xyz"])
    assert len(errs) == 1
    assert "definitely-not-a-real-package-xyz" in errs[0]


def test_check_requirements_ignores_empty():
    assert check_requirements([]) == []


def test_load_artifact_missing_requirement_fails(tmp_artifact: Path, monkeypatch):
    import yaml

    p = tmp_artifact / "manifest.yaml"
    data = yaml.safe_load(p.read_text())
    data["runtime"] = {"requirements": ["definitely-not-a-real-package-xyz"]}
    p.write_text(yaml.safe_dump(data))
    with pytest.raises(RuntimeError, match="requirements not satisfied"):
        load_artifact(tmp_artifact)
