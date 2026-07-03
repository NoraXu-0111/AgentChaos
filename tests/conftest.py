"""Shared pytest fixtures."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agentchaos.trace.recorder import TraceRecorder
from agentchaos.trace.schema import (
    AgentTurn,
    ChaosInjected,
    ModelCall,
    Retry,
    RunEnd,
    RunMeta,
    SessionEnd,
    SessionStart,
    ToolCall,
    ToolResponse,
    TraceEvent,
    UserTurn,
)


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_jsonl(tmp_path: Path) -> Path:
    return tmp_path / "trace.jsonl"


_OTEL_BASE = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)


def _at(seconds: float) -> datetime:
    return _OTEL_BASE + timedelta(seconds=seconds)


@pytest.fixture
def otel_trace_events() -> list[TraceEvent]:
    """Representative trace: run_meta, session_start, 2 turns, model/tool calls (one erroring),
    chaos_injected, retry, tool_response, session_end, run_end. Deterministic timestamps."""
    run_id = "run-otel-1"
    session_id = "sess-1"
    return [
        RunMeta(
            run_id=run_id, seq=0, timestamp=_at(0),
            agentchaos_version="0.1.0",
            scenario_path="scenarios/refund.yaml",
            scenario_hash="sha256:abc123",
            scenario_name="refund-agent",
            seed=42, git_sha="deadbeef",
            started_at=_at(0),
        ),
        SessionStart(
            run_id=run_id, seq=1, timestamp=_at(0.1), session_id=session_id,
            scenario_name="refund-agent",
            agent_target={"type": "http", "endpoint": "http://127.0.0.1:8080/chat"},
        ),
        UserTurn(
            run_id=run_id, seq=2, timestamp=_at(1), session_id=session_id,
            turn_index=0, text="I want to return my order.",
        ),
        ModelCall(
            run_id=run_id, seq=3, timestamp=_at(2), session_id=session_id,
            turn_index=0, call_index=0, name="planner",
            model="gpt-4o-mini", input_tokens=100, output_tokens=20,
            cost_usd=0.001, latency_ms=200, ttft_ms=50, stop_reason="stop",
        ),
        ToolCall(
            run_id=run_id, seq=4, timestamp=_at(3), session_id=session_id,
            turn_index=0, call_index=0, name="get_order",
            args={"id": "1"}, args_hash="hash-get-order",
            latency_ms=None, result_summary="ok", result_size_bytes=128, retries=0,
        ),
        ChaosInjected(
            run_id=run_id, seq=5, timestamp=_at(3.5), session_id=session_id,
            target="get_order", policy="fail-503", injection_type="status_code",
            value=503, tool_name="get_order", args_hash="hash-get-order",
        ),
        Retry(
            run_id=run_id, seq=6, timestamp=_at(4), session_id=session_id,
            turn_index=0, logical_call_index=0, attempt=1,
            reason="503", backoff_ms=100,
        ),
        ToolResponse(
            run_id=run_id, seq=7, timestamp=_at(4.5), session_id=session_id,
            tool_name="get_order", status=200, size_bytes=128,
            chaos_injected=True, args_hash="hash-get-order",
        ),
        AgentTurn(
            run_id=run_id, seq=8, timestamp=_at(5), session_id=session_id,
            turn_index=0, text="Looked up your order.", latency_ms=4000, ttft_ms=500,
            usage={"input_tokens": 100, "output_tokens": 20, "cost_usd": 0.001},
            fidelity="full",
        ),
        UserTurn(
            run_id=run_id, seq=9, timestamp=_at(6), session_id=session_id,
            turn_index=1, text="Send me the label.",
        ),
        ToolCall(
            run_id=run_id, seq=10, timestamp=_at(7), session_id=session_id,
            turn_index=1, call_index=0, name="create_return_label",
            args={"id": "1"}, args_hash="hash-label",
            latency_ms=50, result_summary="error", error="label service boom", retries=1,
        ),
        AgentTurn(
            run_id=run_id, seq=11, timestamp=_at(8), session_id=session_id,
            turn_index=1, text="Sorry, the label failed.", latency_ms=1500,
            usage={"input_tokens": 80, "output_tokens": 15, "cost_usd": 0.001},
            fidelity="full",
        ),
        SessionEnd(
            run_id=run_id, seq=12, timestamp=_at(9), session_id=session_id,
            outcome="completed", turns=2, tool_calls=2, model_calls=1, retries=1,
            total_cost_usd=0.002, total_latency_ms=5500, duration_s=9.0,
        ),
        RunEnd(
            run_id=run_id, seq=13, timestamp=_at(9), session_id=session_id,
            outcome="pass", finished_at=_at(9), exit_code=0,
        ),
    ]


@pytest.fixture
def otel_trace_file(tmp_path: Path, otel_trace_events: list[TraceEvent]) -> Path:
    """The events written as JSONL via TraceRecorder; returns the path."""
    path = tmp_path / "otel-trace.jsonl"
    with TraceRecorder(path) as rec:
        for ev in otel_trace_events:
            rec.write(ev)
    return path
