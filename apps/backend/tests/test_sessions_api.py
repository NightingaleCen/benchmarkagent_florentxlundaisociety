from fastapi.testclient import TestClient


def test_health(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_session(client: TestClient):
    r = client.post("/sessions")
    assert r.status_code == 200
    sid = r.json()["id"]
    assert len(sid) == 12

    r = client.get(f"/sessions/{sid}")
    assert r.status_code == 200
    assert r.json()["id"] == sid


def test_missing_session_returns_404(client: TestClient):
    assert client.get("/sessions/doesnotexist").status_code == 404


def test_delete_session(client: TestClient):
    sid = client.post("/sessions").json()["id"]
    assert client.delete(f"/sessions/{sid}").status_code == 200
    assert client.get(f"/sessions/{sid}").status_code == 404


def test_list_sessions(client: TestClient):
    ids = {client.post("/sessions").json()["id"] for _ in range(3)}
    listed = set(client.get("/sessions").json()["ids"])
    assert ids == listed
