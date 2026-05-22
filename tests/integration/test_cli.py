"""End-to-end CLI tests using a threaded uvicorn FastAPI server."""
from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from typer.testing import CliRunner

from agentchaos.cli import app

pytestmark = pytest.mark.integration


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_ready(url: str, timeout_s: float = 5.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            httpx.get(url, timeout=0.5)
            return
        except Exception:
            time.sleep(0.05)
    raise RuntimeError(f"server at {url} did not become ready")


@pytest.fixture
def happy_server() -> Iterator[str]:
    app_ = FastAPI()

    @app_.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app_.post("/chat")
    def chat(body: dict) -> dict:
        return {
            "session_id": body.get("session_id"),
            "message": "Sure, your refund label is on its way.",
            "agent": {"name": "happy", "version": "0.1", "model": "gpt-4o-mini"},
            "events": [
                {
                    "type": "model_call", "name": "planner", "model": "gpt-4o-mini",
                    "input_tokens": 100, "output_tokens": 20,
                    "cost_usd": 0.001, "latency_ms": 200,
                    "metadata": {"rag_chunks": 5},
                },
                {
                    "type": "tool_call", "name": "get_order",
                    "args": {"id": "1"}, "latency_ms": 50,
                    "result_summary": "ok", "retries": 0,
                },
            ],
            "usage": {"input_tokens": 100, "output_tokens": 20, "cost_usd": 0.001},
        }

    port = _free_port()
    config = uvicorn.Config(app_, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        _wait_ready(f"http://127.0.0.1:{port}/health")
        yield f"http://127.0.0.1:{port}/chat"
    finally:
        server.should_exit = True
        thread.join(timeout=3)


@pytest.fixture
def expensive_server() -> Iterator[str]:
    """Same as happy_server but with higher cost + RAG chunks."""
    app_ = FastAPI()

    @app_.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app_.post("/chat")
    def chat(body: dict) -> dict:
        return {
            "session_id": body.get("session_id"),
            "message": "Sure, your refund label is on its way.",
            "agent": {"name": "happy", "version": "0.1", "model": "gpt-4o-mini"},
            "events": [
                {
                    "type": "model_call", "name": "planner", "model": "gpt-4o-mini",
                    "input_tokens": 400, "output_tokens": 60,
                    "cost_usd": 0.005, "latency_ms": 800,
                    "metadata": {"rag_chunks": 12},
                },
                {
                    "type": "tool_call", "name": "get_order",
                    "args": {"id": "1"}, "latency_ms": 50,
                    "result_summary": "ok", "retries": 3,
                },
                {
                    "type": "tool_call", "name": "get_order",
                    "args": {"id": "1"}, "latency_ms": 60,
                    "result_summary": "ok", "retries": 0,
                },
            ],
            "usage": {"input_tokens": 400, "output_tokens": 60, "cost_usd": 0.005},
        }

    port = _free_port()
    config = uvicorn.Config(app_, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        _wait_ready(f"http://127.0.0.1:{port}/health")
        yield f"http://127.0.0.1:{port}/chat"
    finally:
        server.should_exit = True
        thread.join(timeout=3)


def _write_scenario(path: Path, endpoint: str, *, cost_limit: float = 0.05, rag_limit: bool = False) -> None:
    cost_reg = "  max_cost_regression_pct: 20" if rag_limit else ""
    path.write_text(
        f"""id: t
name: refund-agent
agent:
  type: http
  endpoint: {endpoint}
conversation:
  - user: "I want to return my order."
expect:
  must_call_tools: [get_order]
  final_response_contains: [refund]
budgets:
  max_cost_usd: {cost_limit}
  max_tool_calls: 8
{cost_reg}
"""
    )


# ----------------------------------------------------------------------------


def test_cli_init_creates_files(tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "demo"
    result = runner.invoke(app, ["init", str(out)])
    assert result.exit_code == 0
    assert (out / "scenarios" / "example.yaml").exists()
    assert (out / "runs" / ".gitkeep").exists()
    assert (out / "README.md").exists()


def test_cli_init_refuses_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    runner.invoke(app, ["init", str(tmp_path)])
    result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 1
    assert "refusing to overwrite" in result.stderr or "refusing to overwrite" in result.stdout


def test_cli_init_force_overwrites(tmp_path: Path) -> None:
    runner = CliRunner()
    runner.invoke(app, ["init", str(tmp_path)])
    result = runner.invoke(app, ["init", str(tmp_path), "--force"])
    assert result.exit_code == 0


def test_cli_doctor_reachable(tmp_path: Path, happy_server: str) -> None:
    sc = tmp_path / "s.yaml"
    _write_scenario(sc, happy_server)
    runner = CliRunner()
    result = runner.invoke(app, ["doctor", str(sc)])
    assert result.exit_code == 0
    assert "Endpoint reachable" in result.stdout


def test_cli_doctor_unreachable(tmp_path: Path) -> None:
    sc = tmp_path / "s.yaml"
    _write_scenario(sc, "http://127.0.0.1:1/never_listens")
    runner = CliRunner()
    result = runner.invoke(app, ["doctor", str(sc)])
    assert result.exit_code == 4


def test_cli_doctor_invalid_scenario(tmp_path: Path) -> None:
    sc = tmp_path / "s.yaml"
    sc.write_text("id: x\nname: x\nagent:\n  type: http\n  endpoint: not-a-url\nconversation:\n  - user: hi\n")
    runner = CliRunner()
    result = runner.invoke(app, ["doctor", str(sc)])
    assert result.exit_code == 1


def test_cli_run_pass(tmp_path: Path, happy_server: str) -> None:
    sc = tmp_path / "s.yaml"
    _write_scenario(sc, happy_server, cost_limit=1.0)
    out = tmp_path / "run.jsonl"
    runner = CliRunner()
    result = runner.invoke(app, ["run", str(sc), "--out", str(out)])
    assert result.exit_code == 0
    assert "Verdict: PASS" in result.stdout
    assert out.exists()


def test_cli_run_fail_on_budget(tmp_path: Path, happy_server: str) -> None:
    sc = tmp_path / "s.yaml"
    _write_scenario(sc, happy_server, cost_limit=0.0001)
    out = tmp_path / "run.jsonl"
    runner = CliRunner()
    result = runner.invoke(app, ["run", str(sc), "--out", str(out)])
    assert result.exit_code == 2
    assert "Verdict: FAIL" in result.stdout


def test_cli_run_with_baseline(
    tmp_path: Path, happy_server: str, expensive_server: str
) -> None:
    sc_base = tmp_path / "s.yaml"
    _write_scenario(sc_base, happy_server, cost_limit=1.0, rag_limit=True)
    baseline = tmp_path / "baseline.jsonl"
    runner = CliRunner()
    # Record baseline against happy server.
    r1 = runner.invoke(app, ["run", str(sc_base), "--out", str(baseline)])
    assert r1.exit_code == 0

    # Re-point scenario at expensive_server and re-run with --baseline.
    _write_scenario(sc_base, expensive_server, cost_limit=1.0, rag_limit=True)
    candidate = tmp_path / "candidate.jsonl"
    r2 = runner.invoke(
        app,
        ["run", str(sc_base), "--out", str(candidate), "--baseline", str(baseline)],
    )
    # The expensive server returns ~5x the cost; this should trigger the
    # 20% regression budget.
    assert r2.exit_code == 2
    assert "regression_budget" in r2.stdout or "regressed" in r2.stdout


def test_cli_run_json_output(tmp_path: Path, happy_server: str) -> None:
    import json as _json
    sc = tmp_path / "s.yaml"
    _write_scenario(sc, happy_server, cost_limit=1.0)
    out = tmp_path / "run.jsonl"
    runner = CliRunner()
    result = runner.invoke(app, ["run", str(sc), "--out", str(out), "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["outcome"] == "pass"
    assert payload["exit_code"] == 0
    assert "run_id" in payload


def test_cli_compare_two_traces(
    tmp_path: Path, happy_server: str, expensive_server: str
) -> None:
    runner = CliRunner()
    sc1 = tmp_path / "s.yaml"
    _write_scenario(sc1, happy_server)
    base = tmp_path / "base.jsonl"
    runner.invoke(app, ["run", str(sc1), "--out", str(base), "--quiet"])

    sc2 = tmp_path / "s2.yaml"
    _write_scenario(sc2, expensive_server)
    cand = tmp_path / "cand.jsonl"
    runner.invoke(app, ["run", str(sc2), "--out", str(cand), "--quiet"])

    result = runner.invoke(app, ["compare", str(base), str(cand)])
    assert result.exit_code == 0
    assert "Metrics" in result.stdout
    assert "Possible contributors" in result.stdout or "metadata" in result.stdout


def test_cli_compare_missing_file(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["compare", str(tmp_path / "no.jsonl"), str(tmp_path / "no2.jsonl")])
    assert result.exit_code == 1
