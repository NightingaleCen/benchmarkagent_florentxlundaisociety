from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.config as config_mod
from backend.main import create_app


@pytest.fixture(autouse=True)
def isolated_sessions(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BMK_SESSIONS_ROOT", str(tmp_path / "sessions"))
    config_mod._settings = None
    yield
    config_mod._settings = None


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())
