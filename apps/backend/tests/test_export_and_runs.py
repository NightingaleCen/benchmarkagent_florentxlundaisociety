import io
import zipfile

from fastapi.testclient import TestClient

MANIFEST = """
schema_version: "0.1"
name: api-test
description: api test
task:
  type: binary_classification
  input_schema:
    text: { type: string }
  output_schema:
    label: { type: string, enum: ["yes", "no"] }
evaluator:
  judge:
    type: rule
dataset:
  path: dataset.jsonl
  count: 1
"""

DATASET = '{"input": {"text": "hi"}, "expected": {"label": "yes"}}\n'

ADAPTER = """
def run_model(model_client, input_record):
    return {"output": {"label": "yes"}, "usage": {"input_tokens": 1, "output_tokens": 1}, "latency_ms": 0, "raw_response": None}
"""

EVALUATOR = """
def evaluate(model_output, expected, judge=None):
    s = 1 if model_output.get("label") == expected.get("label") else 0
    return {"score": s, "reason": "x"}
"""


def _seed(client: TestClient) -> str:
    sid = client.post("/sessions").json()["id"]
    client.put(f"/sessions/{sid}/artifact/manifest.yaml", json={"content": MANIFEST})
    client.put(f"/sessions/{sid}/artifact/dataset.jsonl", json={"content": DATASET})
    client.put(f"/sessions/{sid}/artifact/adapter.py", json={"content": ADAPTER})
    client.put(f"/sessions/{sid}/artifact/evaluator.py", json={"content": EVALUATOR})
    return sid


def test_export_zip_contains_all_files(client: TestClient):
    sid = _seed(client)
    client.put(
        f"/sessions/{sid}/artifact/__pycache__/adapter.cpython-312.pyc",
        json={"content": "binary-looking-cache"},
    )
    r = client.get(f"/sessions/{sid}/export")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = set(zf.namelist())
    assert {"manifest.yaml", "dataset.jsonl", "adapter.py", "evaluator.py"} <= names
    assert "__pycache__/adapter.cpython-312.pyc" not in names


def test_export_empty_artifact_fails(client: TestClient):
    sid = client.post("/sessions").json()["id"]
    r = client.get(f"/sessions/{sid}/export")
    assert r.status_code == 400


def test_import_zip_populates_artifact(client: TestClient):
    sid = client.post("/sessions").json()["id"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.yaml", MANIFEST)
        zf.writestr("dataset.jsonl", DATASET)
        zf.writestr("adapter.py", ADAPTER)
        zf.writestr("evaluator.py", EVALUATOR)
        zf.writestr("__pycache__/evaluator.cpython-312.pyc", b"\xcbbinary")
    buf.seek(0)

    r = client.post(
        f"/sessions/{sid}/export/import",
        files={"file": ("benchmark.zip", buf.getvalue(), "application/zip")},
    )
    assert r.status_code == 200
    assert set(r.json()["files"]) == {
        "manifest.yaml",
        "dataset.jsonl",
        "adapter.py",
        "evaluator.py",
    }

    files = set(client.get(f"/sessions/{sid}/artifact").json()["files"])
    assert files == {"manifest.yaml", "dataset.jsonl", "adapter.py", "evaluator.py"}


def test_trigger_run_with_stub_model(client: TestClient, monkeypatch):
    """Patch build_model_client so we don't need an API key. The adapter
    doesn't call the model in this test, but the runner still builds a client."""
    from benchmarkrun import runtime as rt

    class _Stub:
        model_id = "fake"
        raw_client = None

    monkeypatch.setattr(
        rt, "build_model_client", lambda m, *, provider=None: _Stub()
    )

    sid = _seed(client)
    r = client.post(f"/sessions/{sid}/runs", json={"model": "fake"})
    assert r.status_code == 200
    data = r.json()
    assert data["summary"]["count"] == 1
    assert data["summary"]["passed"] == 1

    runs = client.get(f"/sessions/{sid}/runs").json()["runs"]
    assert len(runs) == 1
