"""End-to-end smoke test of the refund-agent demo.

Spins up the demo's FastAPI server in a thread, records a baseline against
``rag_chunks=5`` and a candidate against ``rag_chunks=12``, and asserts the
CLI flags the cost regression with a metadata.rag_chunks contributor.
"""
from __future__ import annotations

import socket
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn
from typer.testing import CliRunner

from agentchaos.cli import app

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def server() -> Iterator[str]:
    # Make examples/refund-agent importable.
    repo_root = Path(__file__).resolve().parent.parent.parent
    demo_dir = repo_root / "examples" / "refund-agent"
    sys.path.insert(0, str(demo_dir))
    try:
        from server.main import app as fastapi_app  # type: ignore[import-not-found]
    finally:
        sys.path.pop(0)

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    config = uvicorn.Config(fastapi_app, host="127.0.0.1", port=port, log_level="error")
    server_obj = uvicorn.Server(config)
    thread = threading.Thread(target=server_obj.run, daemon=True)
    thread.start()
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5)
            break
        except Exception:
            time.sleep(0.05)
    else:
        raise RuntimeError("demo server failed to start")
    yield f"http://127.0.0.1:{port}"
    server_obj.should_exit = True
    thread.join(timeout=3)


def _write_scenario(path: Path, endpoint: str) -> None:
    path.write_text(
        f"""id: refund-rag-cost-regression
name: refund-rag-cost-regression
agent:
  type: http
  endpoint: "{endpoint}"
  timeout_s: 10
conversation:
  - user: "I want to return my order."
  - user: "My order number is 12345."
expect:
  must_call_tools: [get_order, create_return_label]
  final_response_contains: [return label]
budgets:
  max_cost_usd: 0.05
  max_tool_calls: 6
  max_llm_calls: 4
  max_cost_regression_pct: 20
  max_input_token_regression_pct: 30
"""
    )


def test_demo_catches_rag_chunks_regression(tmp_path: Path, server: str) -> None:
    runner = CliRunner()
    # 1. baseline at rag_chunks=5
    httpx.post(f"{server}/control/reset")
    sc_baseline = tmp_path / "baseline_scenario.yaml"
    _write_scenario(sc_baseline, f"{server}/chat?rag_chunks=5")
    baseline = tmp_path / "baseline.jsonl"
    r1 = runner.invoke(app, ["run", str(sc_baseline), "--out", str(baseline), "--quiet"])
    assert r1.exit_code == 0, r1.stdout

    # 2. candidate at rag_chunks=12 — same scenario, different rag_chunks
    httpx.post(f"{server}/control/reset")
    sc_candidate = tmp_path / "candidate_scenario.yaml"
    _write_scenario(sc_candidate, f"{server}/chat?rag_chunks=12")
    candidate = tmp_path / "candidate.jsonl"
    r2 = runner.invoke(
        app,
        ["run", str(sc_candidate), "--out", str(candidate), "--baseline", str(baseline)],
    )
    assert r2.exit_code == 2, f"expected FAIL, got\n{r2.stdout}"

    # 3. The report should mention rag_chunks as a contributor.
    out = r2.stdout
    assert "Verdict: FAIL" in out
    assert "regression_budget" in out
    assert "rag_chunks" in out
    assert "5" in out and "12" in out


def _write_retry_storm_scenario(path: Path, endpoint: str) -> None:
    path.write_text(
        f"""id: refund-retry-storm
name: refund-retry-storm
agent:
  type: http
  endpoint: "{endpoint}"
  timeout_s: 10
conversation:
  - user: "I want to return my order."
  - user: "My order number is 12345."
expect:
  must_call_tools: [get_order]
budgets:
  max_loop_repetitions: 3
  loop_window: 8
"""
    )


def test_retry_storm_scenario_fires_loop_detector(tmp_path: Path, server: str) -> None:
    runner = CliRunner()
    httpx.post(f"{server}/control/reset")
    sc = tmp_path / "retry_storm.yaml"
    _write_retry_storm_scenario(sc, f"{server}/chat?retry_storm=5")
    out_path = tmp_path / "trace.jsonl"
    res = runner.invoke(app, ["run", str(sc), "--out", str(out_path)])
    assert res.exit_code == 2, f"expected exit 2, got\n{res.stdout}"
    out = res.stdout
    assert "Verdict: FAIL" in out
    assert "Detected patterns" in out
    assert "loop" in out
    assert "max_loop_repetitions" in out
