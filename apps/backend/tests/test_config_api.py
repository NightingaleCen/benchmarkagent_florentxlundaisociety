from fastapi.testclient import TestClient


def test_config_returns_default_model(client: TestClient):
    r = client.get("/config")
    assert r.status_code == 200
    data = r.json()
    assert "orchestrator_model_default" in data
    assert "max_agent_iterations" in data
    assert data["orchestrator_model_default"]  # non-empty


def test_config_respects_env_override(monkeypatch, client: TestClient):
    import backend.config as config_mod

    monkeypatch.setenv("BMK_ORCHESTRATOR_MODEL", "claude-opus-4-7")
    config_mod._settings = None  # force reload

    r = client.get("/config")
    assert r.json()["orchestrator_model_default"] == "claude-opus-4-7"
