from fastapi.testclient import TestClient


def test_write_and_read_file(client: TestClient):
    sid = client.post("/sessions").json()["id"]

    r = client.put(
        f"/sessions/{sid}/artifact/manifest.yaml",
        json={"content": "name: demo\n"},
    )
    assert r.status_code == 200

    r = client.get(f"/sessions/{sid}/artifact/manifest.yaml")
    assert r.status_code == 200
    assert r.json()["content"] == "name: demo\n"


def test_list_after_writes(client: TestClient):
    sid = client.post("/sessions").json()["id"]
    client.put(f"/sessions/{sid}/artifact/manifest.yaml", json={"content": "x"})
    client.put(f"/sessions/{sid}/artifact/adapter.py", json={"content": "y"})
    files = client.get(f"/sessions/{sid}/artifact").json()["files"]
    assert set(files) == {"manifest.yaml", "adapter.py"}


def test_read_missing_file(client: TestClient):
    sid = client.post("/sessions").json()["id"]
    r = client.get(f"/sessions/{sid}/artifact/nope.yaml")
    assert r.status_code == 404


def test_rejects_path_escape_via_safe_relpath():
    """HTTP URL normalization already collapses '..' before routing, so we
    test the in-process defense directly against crafted payloads."""
    import pytest

    from backend.sessions import _safe_relpath

    with pytest.raises(ValueError):
        _safe_relpath("../outside.txt")
    with pytest.raises(ValueError):
        _safe_relpath("/abs/path")
    with pytest.raises(ValueError):
        _safe_relpath("nested/../../etc/passwd")
    with pytest.raises(ValueError):
        _safe_relpath("a\x00b")
    # valid paths pass through
    assert str(_safe_relpath("manifest.yaml")) == "manifest.yaml"
    assert str(_safe_relpath("sub/dir/file.py")) == "sub/dir/file.py"
