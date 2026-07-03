"""End-to-end CLI tests for `agentchaos replay` using threaded uvicorn servers."""
from __future__ import annotations

import json as _json
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
from agentchaos.profile.metrics import aggregate
from agentchaos.trace.reader import read_trace

pytestmark = pytest.mark.integration

_UNBOUND_ENDPOINT = "http://127.0.0.1:9/chat"


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


def _make_agent_app(second_tool: str) -> FastAPI:
    app_ = FastAPI()

    @app_.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app_.post("/chat")
    def chat(body: dict) -> dict:
        return {
            "session_id": body.get("session_id"),
            "message": "Sure, your refund label is on its way.",
            "agent": {"name": "refund", "version": "0.1", "model": "gpt-4o-mini"},
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
                {
                    "type": "tool_call", "name": second_tool,
                    "args": {"id": "1"}, "latency_ms": 50,
                    "result_summary": "ok", "retries": 0,
                },
            ],
            "usage": {"input_tokens": 100, "output_tokens": 20, "cost_usd": 0.001},
        }

    return app_


def _serve(app_: FastAPI) -> Iterator[str]:
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
def agent_v1() -> Iterator[str]:
    """Calls get_order then create_return_label."""
    yield from _serve(_make_agent_app("create_return_label"))


@pytest.fixture
def agent_v2_changed() -> Iterator[str]:
    """The intentional agent change: get_order then lookup_customer."""
    yield from _serve(_make_agent_app("lookup_customer"))


def _write_scenario(
    path: Path,
    endpoint: str,
    *,
    turns: list[str] | None = None,
    chaos: bool = False,
) -> None:
    turn_lines = "\n".join(
        f'  - user: "{t}"' for t in (turns or ["I want to return my order."])
    )
    chaos_block = ""
    if chaos:
        chaos_block = (
            "chaos:\n"
            "  targets:\n"
            "    - tool: get_order\n"
            "      policy:\n"
            "        failure_rate: 1.0\n"
            "        status_code: 503\n"
        )
    path.write_text(
        f"""id: t
name: refund-agent
agent:
  type: http
  endpoint: {endpoint}
conversation:
{turn_lines}
expect:
  must_call_tools: [get_order]
budgets:
  max_cost_usd: 1.0
  max_tool_calls: 8
{chaos_block}"""
    )


def _record(runner: CliRunner, scenario: Path, out: Path) -> None:
    result = runner.invoke(app, ["run", str(scenario), "--out", str(out), "--quiet"])
    assert result.exit_code == 0, result.output


# ----------------------------------------------------------------------------


def test_offline_replay_is_deterministic_and_needs_no_server(
    tmp_path: Path, agent_v1: str
) -> None:
    runner = CliRunner()
    sc = tmp_path / "s.yaml"
    _write_scenario(sc, agent_v1)
    recording = tmp_path / "recording.jsonl"
    _record(runner, sc, recording)

    # Point the scenario at a dead endpoint: offline replay must not need it.
    _write_scenario(sc, _UNBOUND_ENDPOINT)
    replayed = tmp_path / "replayed.jsonl"
    result = runner.invoke(
        app,
        ["replay", str(sc), str(recording), "--out", str(replayed), "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["outcome"] == "pass"
    assert payload["divergences"] == []
    assert payload["mode"] == "offline"

    recorded_metrics = aggregate(read_trace(recording))
    replayed_metrics = aggregate(read_trace(replayed))
    assert replayed_metrics.total_cost_usd == recorded_metrics.total_cost_usd
    assert replayed_metrics.tool_calls == recorded_metrics.tool_calls
    assert replayed_metrics.llm_calls == recorded_metrics.llm_calls
    assert replayed_metrics.tool_sequence == recorded_metrics.tool_sequence


def test_live_replay_of_changed_agent_exits_5(
    tmp_path: Path, agent_v1: str, agent_v2_changed: str
) -> None:
    runner = CliRunner()
    sc = tmp_path / "s.yaml"
    _write_scenario(sc, agent_v1)
    recording = tmp_path / "recording.jsonl"
    _record(runner, sc, recording)

    # The "intentional agent change": same scenario, different agent behavior.
    _write_scenario(sc, agent_v2_changed)
    result = runner.invoke(
        app,
        [
            "replay", str(sc), str(recording), "--live", "--json",
            "--out", str(tmp_path / "live.jsonl"),
        ],
    )
    assert result.exit_code == 5, result.output
    payload = _json.loads(result.stdout)
    assert payload["outcome"] == "fail"
    assert payload["mode"] == "live"
    assert payload["divergences"]
    assert any(d["kind"] == "tool_call_mismatch" for d in payload["divergences"])

    # Terminal variant shows [replay] in the "Why" block.
    result_term = runner.invoke(
        app,
        [
            "replay", str(sc), str(recording), "--live",
            "--out", str(tmp_path / "live2.jsonl"),
        ],
    )
    assert result_term.exit_code == 5
    assert "[replay]" in result_term.stdout


def test_replay_missing_recording_exits_1(tmp_path: Path) -> None:
    runner = CliRunner()
    sc = tmp_path / "s.yaml"
    _write_scenario(sc, _UNBOUND_ENDPOINT)
    result = runner.invoke(app, ["replay", str(sc), str(tmp_path / "missing.jsonl")])
    assert result.exit_code == 1


def test_replay_recording_with_no_turns_exits_1(tmp_path: Path) -> None:
    runner = CliRunner()
    sc = tmp_path / "s.yaml"
    _write_scenario(sc, _UNBOUND_ENDPOINT)
    recording = tmp_path / "meta-only.jsonl"
    recording.write_text(
        _json.dumps(
            {
                "schema_version": "1",
                "run_id": "r",
                "seq": 0,
                "timestamp": "2026-07-01T12:00:00Z",
                "kind": "run_meta",
                "agentchaos_version": "0.1.0",
                "scenario_path": "s.yaml",
                "scenario_hash": "sha256:abc",
                "scenario_name": "refund-agent",
                "started_at": "2026-07-01T12:00:00Z",
            }
        )
        + "\n"
    )
    result = runner.invoke(app, ["replay", str(sc), str(recording)])
    assert result.exit_code == 1
    combined = result.stdout + (result.stderr or "")
    assert "no conversation turns" in combined


def test_replay_scenario_with_extra_turn_exits_5(tmp_path: Path, agent_v1: str) -> None:
    runner = CliRunner()
    two_turns = ["I want to return my order.", "Send me the label."]
    sc = tmp_path / "s.yaml"
    _write_scenario(sc, agent_v1, turns=two_turns)
    recording = tmp_path / "recording.jsonl"
    _record(runner, sc, recording)

    _write_scenario(sc, _UNBOUND_ENDPOINT, turns=[*two_turns, "One more thing."])
    result = runner.invoke(
        app,
        [
            "replay", str(sc), str(recording), "--json",
            "--out", str(tmp_path / "replayed.jsonl"),
        ],
    )
    assert result.exit_code == 5, result.output
    payload = _json.loads(result.stdout)
    assert any(d["kind"] == "turn_count_mismatch" for d in payload["divergences"])


def test_replay_strips_chaos_block(tmp_path: Path, agent_v1: str) -> None:
    runner = CliRunner()
    sc = tmp_path / "s.yaml"
    _write_scenario(sc, agent_v1)
    recording = tmp_path / "recording.jsonl"
    _record(runner, sc, recording)

    _write_scenario(sc, _UNBOUND_ENDPOINT, chaos=True)
    replayed = tmp_path / "replayed.jsonl"
    result = runner.invoke(
        app,
        ["replay", str(sc), str(recording), "--out", str(replayed), "--json"],
    )
    assert result.exit_code == 0, result.output
    kinds = {e.kind for e in read_trace(replayed)}
    assert "chaos_injected" not in kinds
