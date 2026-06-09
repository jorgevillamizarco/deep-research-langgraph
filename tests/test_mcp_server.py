"""HTTP/MCP surface tests for the deep research server."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType

from starlette.testclient import TestClient


def test_mcp_post_initialize_and_tools_list():
    """POST /mcp supports initialize and tools/list without SSE."""
    from app.mcp_server import create_http_app

    client = TestClient(create_http_app())

    init = client.post("/mcp", json={
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {},
    })
    assert init.status_code == 200
    assert init.json()["result"]["serverInfo"]["name"] == "deep-research"

    tools = client.post("/mcp", json={
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    })
    tool_names = {tool["name"] for tool in tools.json()["result"]["tools"]}
    assert {"search", "deep_research", "research_status"}.issubset(tool_names)


def test_tasks_api_includes_persisted_tasks(tmp_path, monkeypatch):
    """Dashboard task API includes persisted tasks after restart."""
    import app.mcp_server as mcp_server

    report_path = tmp_path / "report_test.md"
    report_path.write_text("# Report")
    meta_path = tmp_path / "task_research-persisted123.json"
    meta_path.write_text(json.dumps({
        "task_id": "research-persisted123",
        "topic": "Persisted topic",
        "status": "completed",
        "progress": 1.0,
        "created_at": 1000,
        "completed_at": 1100,
        "stage": "report_critic",
        "report_critic_passed": False,
        "report_critic_result": {"hard_failures": [], "warnings": ["low confidence claims"]},
        "report_path": str(report_path),
        "char_count": 8,
    }))

    monkeypatch.setattr(mcp_server, "_get_report_dir", lambda: tmp_path)
    mcp_server._research_tasks.clear()

    client = TestClient(mcp_server.create_http_app())
    resp = client.get("/tasks")
    assert resp.status_code == 200
    tasks = resp.json()
    task_ids = {task["task_id"] for task in tasks}
    assert "research-persisted123" in task_ids
    persisted = next(task for task in tasks if task["task_id"] == "research-persisted123")
    assert persisted["has_report"] is True
    assert persisted["report_filename"] == "report_test.md"
    assert persisted["stage"] == "Running final report QA"
    assert persisted["report_critic_passed"] is False
    assert persisted["report_critic_result"]["warnings"] == ["low confidence claims"]
    assert "report_path" not in persisted
    assert "pdf_path" not in persisted


def test_format_elapsed_minutes():
    """Elapsed UI labels should render in minutes, not seconds."""
    import app.mcp_server as mcp_server

    assert mcp_server._format_elapsed_minutes(30) == "0.5m"
    assert mcp_server._format_elapsed_minutes(90) == "1.5m"
    assert mcp_server._format_elapsed_minutes(600) == "10m"


def test_tasks_api_freezes_elapsed_for_finished_tasks(tmp_path, monkeypatch):
    """Completed tasks should stop incrementing elapsed time in the dashboard."""
    import app.mcp_server as mcp_server

    report_path = tmp_path / "report_test.md"
    report_path.write_text("# Report")
    for status in ("completed", "failed"):
        task = {
            "task_id": f"research-finished-{status}",
            "topic": "Finished topic",
            "status": status,
            "progress": 1.0,
            "created_at": 1000,
            "completed_at": 1100,
            "stage": "report_critic",
            "report_path": str(report_path),
        }

        assert mcp_server._task_api_view(task, now=2000)["elapsed"] == 100


def test_ready_endpoint_reports_dependency_status(monkeypatch, tmp_path):
    """Readiness endpoint reports ok only when runtime dependencies are reachable."""
    import app.mcp_server as mcp_server

    monkeypatch.setenv("WORKER_API_KEY", "test-key")
    monkeypatch.setenv("WORKER_API_BASE", "https://api.example.com")
    monkeypatch.setattr(mcp_server, "_get_report_dir", lambda: tmp_path)
    monkeypatch.setattr(mcp_server, "_probe_llm_api", lambda: {"ok": True, "detail": "reachable"})
    monkeypatch.setattr(mcp_server, "_probe_search_backend", lambda: {"ok": True, "detail": "searxng"})
    monkeypatch.setattr(mcp_server, "_probe_checkpoint_db", lambda: {"ok": True, "detail": str(tmp_path / "checkpoints.db")})

    client = TestClient(mcp_server.create_http_app())
    resp = client.get("/ready")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"
    assert payload["checks"]["llm_api"]["ok"] is True


def test_probe_llm_api_requires_success_status(monkeypatch):
    """401/404 responses from the model endpoint must fail readiness."""
    import httpx
    import app.mcp_server as mcp_server

    class FakeClient:
        def __init__(self, status_code):
            self.status_code = status_code

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, headers=None):
            return httpx.Response(self.status_code, request=httpx.Request("GET", url))

    monkeypatch.setenv("WORKER_API_KEY", "test-key")
    monkeypatch.setenv("WORKER_API_BASE", "https://api.example.com")
    monkeypatch.setattr(httpx, "Client", lambda *args, **kwargs: FakeClient(401))
    assert mcp_server._probe_llm_api()["ok"] is False

    monkeypatch.setattr(httpx, "Client", lambda *args, **kwargs: FakeClient(200))
    assert mcp_server._probe_llm_api()["ok"] is True


def test_probe_search_backend_requires_real_tavily_call(monkeypatch):
    """A present Tavily API key is insufficient if the backend call itself fails."""
    import app.mcp_server as mcp_server

    fake_root = ModuleType("langchain_community")
    fake_tools = ModuleType("langchain_community.tools")
    fake_tavily = ModuleType("langchain_community.tools.tavily_search")

    class FakeTavilySearchResults:
        def __init__(self, **kwargs):
            pass

        def invoke(self, params):
            raise RuntimeError("bad tavily key")

    setattr(fake_tavily, "TavilySearchResults", FakeTavilySearchResults)
    monkeypatch.setitem(sys.modules, "langchain_community", fake_root)
    monkeypatch.setitem(sys.modules, "langchain_community.tools", fake_tools)
    monkeypatch.setitem(sys.modules, "langchain_community.tools.tavily_search", fake_tavily)
    monkeypatch.setenv("TAVILY_API_KEY", "dummy")

    probe = mcp_server._probe_search_backend()
    assert probe["ok"] is False
    assert "tavily" in probe["detail"]


def test_tasks_endpoint_allows_private_network_client(tmp_path, monkeypatch):
    """Dashboard APIs remain reachable from local/private bridge addresses."""
    import app.mcp_server as mcp_server

    monkeypatch.setenv("RESEARCH_OUTPUT_DIR", str(tmp_path))
    app = mcp_server.create_http_app()
    client = TestClient(app, client=("172.18.0.1", 50000))

    resp = client.get("/tasks")

    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_dashboard_routes_are_local_only_by_default(monkeypatch):
    """Dashboard/task/download endpoints reject non-local clients unless explicitly opened."""
    import app.mcp_server as mcp_server

    monkeypatch.delenv("DASHBOARD_PUBLIC", raising=False)
    client = TestClient(mcp_server.create_http_app(), client=("203.0.113.10", 1234))

    assert client.get("/").status_code == 403
    assert client.get("/tasks").status_code == 403
    assert client.get("/stream/research-foo").status_code == 403


def test_dashboard_routes_ignore_spoofed_forwarded_headers(monkeypatch):
    """Host/X-Forwarded-For spoofing must not bypass local-only dashboard gates."""
    import app.mcp_server as mcp_server

    monkeypatch.delenv("DASHBOARD_PUBLIC", raising=False)
    client = TestClient(mcp_server.create_http_app(), client=("203.0.113.10", 1234))

    assert client.get("/tasks", headers={"x-forwarded-for": "127.0.0.1"}).status_code == 403
    assert client.get("/tasks", headers={"host": "localhost:8100"}).status_code == 403


def test_download_rejects_path_traversal(tmp_path, monkeypatch):
    """Download endpoint forbids escaping the report directory."""
    import app.mcp_server as mcp_server

    monkeypatch.setattr(mcp_server, "_get_report_dir", lambda: tmp_path)

    client = TestClient(mcp_server.create_http_app())
    resp = client.get("/download/%2E%2E/etc/passwd")
    assert resp.status_code == 403


def test_get_report_dir_defaults_to_home_research(monkeypatch, tmp_path):
    """Unset RESEARCH_OUTPUT_DIR falls back to ~/research before cwd."""
    import app.mcp_server as mcp_server

    monkeypatch.delenv("RESEARCH_OUTPUT_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    report_dir = mcp_server._get_report_dir()

    assert report_dir == tmp_path / "research"


def test_stream_endpoint_emits_completed_event_for_completed_task():
    """Stream endpoint immediately terminates for already-completed tasks."""
    import app.mcp_server as mcp_server

    task_id = "research-complete123"
    mcp_server._research_tasks.clear()
    mcp_server._research_tasks[task_id] = {
        "task_id": task_id,
        "topic": "Done",
        "status": "completed",
        "progress": 1.0,
        "created_at": 1,
    }

    client = TestClient(mcp_server.create_http_app())
    with client.stream("GET", f"/stream/{task_id}") as resp:
        body = b"".join(resp.iter_bytes())

    text = body.decode("utf-8")
    assert "event: started" in text
    assert "event: completed" in text


def test_dashboard_page_loads():
    """Dashboard root serves the web UI."""
    from app.mcp_server import create_http_app

    client = TestClient(create_http_app())
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Deep Research" in resp.text