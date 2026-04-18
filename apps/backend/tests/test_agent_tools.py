from backend.agent.tools import build_tools
from backend.sessions import SessionStore


def _tool_map(tmp_path, allow_agent_data_access: bool):
    store = SessionStore(tmp_path / "sessions")
    session = store.create()
    tools = build_tools(
        store.get(session.id),
        allow_agent_data_access=allow_agent_data_access,
    )
    return {tool.name: tool for tool in tools}, store.get(session.id)


def test_data_paths_blocked_when_agent_data_access_disabled(tmp_path):
    tools, session = _tool_map(tmp_path, allow_agent_data_access=False)
    session.write_artifact_file("dataset.jsonl", '{"input": {"x": 1}}\n')

    read_result = tools["read_artifact_file"].handler({"path": "dataset.jsonl"})
    write_result = tools["write_artifact_file"].handler(
        {"path": "dataset.jsonl", "content": "new data"}
    )
    dry_run_result = tools["dry_run"].handler({})

    assert "disabled for dataset files" in read_result
    assert "disabled for dataset files" in write_result
    assert "dry_run is unavailable" in dry_run_result


def test_data_paths_allowed_when_agent_data_access_enabled(tmp_path):
    tools, session = _tool_map(tmp_path, allow_agent_data_access=True)
    session.write_artifact_file("dataset.jsonl", '{"input": {"x": 1}}\n')

    read_result = tools["read_artifact_file"].handler({"path": "dataset.jsonl"})

    assert '"ok": true' in read_result.lower()
