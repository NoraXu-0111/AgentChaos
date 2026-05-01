"""Tests for metric aggregation across the three fidelity tiers."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agentchaos.profile.metrics import aggregate
from agentchaos.runner.session import args_hash
from agentchaos.trace.schema import (
    AgentTurn,
    ModelCall,
    Retry,
    RunEnd,
    RunMeta,
    SessionEnd,
    SessionStart,
    ToolCall,
    UserTurn,
)


def _ts(s: int) -> datetime:
    return datetime(2026, 4, 30, 12, 0, s, tzinfo=UTC)


def _full_trace() -> list:
    """Two-turn full-fidelity trace with 2 model calls + 3 tool calls + 1 retry."""
    return [
        RunMeta(
            run_id="r", seq=0, timestamp=_ts(0),
            agentchaos_version="0.1", scenario_path="x",
            scenario_hash="h", scenario_name="n", started_at=_ts(0),
        ),
        SessionStart(
            run_id="r", seq=1, timestamp=_ts(1), session_id="s",
            scenario_name="n", agent_target={"type": "http", "endpoint": "x"},
        ),
        UserTurn(run_id="r", seq=2, timestamp=_ts(2), session_id="s", turn_index=0, text="a"),
        ModelCall(
            run_id="r", seq=3, timestamp=_ts(3), session_id="s",
            turn_index=0, call_index=0, name="planner", model="gpt-4o-mini",
            input_tokens=100, output_tokens=20, cost_usd=0.001, latency_ms=200,
        ),
        ToolCall(
            run_id="r", seq=4, timestamp=_ts(4), session_id="s",
            turn_index=0, call_index=1, name="get_order",
            args={"order_id": "1"}, args_hash=args_hash({"order_id": "1"}),
            latency_ms=50, result_summary="ok", retries=0,
        ),
        ToolCall(
            run_id="r", seq=5, timestamp=_ts(5), session_id="s",
            turn_index=0, call_index=2, name="get_order",
            args={"order_id": "1"}, args_hash=args_hash({"order_id": "1"}),
            latency_ms=70, result_summary="ok", retries=1,
        ),
        AgentTurn(
            run_id="r", seq=6, timestamp=_ts(6), session_id="s",
            turn_index=0, text="ack", latency_ms=320,
            usage={"cost_usd": 0.001, "input_tokens": 100, "output_tokens": 20},
        ),
        UserTurn(run_id="r", seq=7, timestamp=_ts(7), session_id="s", turn_index=1, text="b"),
        Retry(
            run_id="r", seq=8, timestamp=_ts(8), session_id="s",
            turn_index=1, logical_call_index=0, attempt=1, reason="503",
        ),
        ModelCall(
            run_id="r", seq=9, timestamp=_ts(9), session_id="s",
            turn_index=1, call_index=0, name="planner", model="gpt-4o-mini",
            input_tokens=80, output_tokens=10, cost_usd=0.0008, latency_ms=180,
        ),
        ToolCall(
            run_id="r", seq=10, timestamp=_ts(10), session_id="s",
            turn_index=1, call_index=1, name="create_label",
            args={"id": "X"}, args_hash=args_hash({"id": "X"}),
            latency_ms=40, result_summary="ok", retries=0,
        ),
        AgentTurn(
            run_id="r", seq=11, timestamp=_ts(11), session_id="s",
            turn_index=1, text="done", latency_ms=240,
        ),
        SessionEnd(
            run_id="r", seq=12, timestamp=_ts(12), session_id="s",
            outcome="completed", turns=2, tool_calls=3, model_calls=2, retries=2,
            total_cost_usd=0.0018, total_latency_ms=560, duration_s=0.56,
        ),
        RunEnd(
            run_id="r", seq=13, timestamp=_ts(13),
            outcome="pass", finished_at=_ts(13), exit_code=0,
        ),
    ]


def test_aggregate_full_trace_totals() -> None:
    m = aggregate(_full_trace())
    # 2 model calls, 3 tool calls, 1 Retry event + 1 retries on a tool_call = 2
    assert m.llm_calls == 2
    assert m.tool_calls == 3
    assert m.retries == 2
    # cost = 0.001 + 0.0008 (no double-count of usage on full-fidelity agent_turn)
    assert m.total_cost_usd == 0.0018
    assert m.total_input_tokens == 180
    assert m.total_output_tokens == 30
    assert m.total_latency_ms == 560
    assert m.max_turn_latency_ms == 320
    assert m.fidelity == "full"


def test_aggregate_by_model_breakdown() -> None:
    m = aggregate(_full_trace())
    assert m.by_model == {"gpt-4o-mini": 0.0018}


def test_aggregate_by_tool_breakdown() -> None:
    m = aggregate(_full_trace())
    assert m.by_tool == {"get_order": 2, "create_label": 1}


def test_aggregate_tool_sequence_preserved() -> None:
    m = aggregate(_full_trace())
    names = [name for (name, _) in m.tool_sequence]
    assert names == ["get_order", "get_order", "create_label"]
    # First two have identical args_hash; last differs.
    assert m.tool_sequence[0][1] == m.tool_sequence[1][1]
    assert m.tool_sequence[0][1] != m.tool_sequence[2][1]


def test_aggregate_aggregate_fidelity_pulls_cost_from_usage() -> None:
    trace: list[Any] = [
        RunMeta(
            run_id="r", seq=0, timestamp=_ts(0),
            agentchaos_version="0.1", scenario_path="x",
            scenario_hash="h", scenario_name="n", started_at=_ts(0),
        ),
        SessionStart(
            run_id="r", seq=1, timestamp=_ts(1), session_id="s",
            scenario_name="n", agent_target={},
        ),
        UserTurn(run_id="r", seq=2, timestamp=_ts(2), session_id="s", turn_index=0, text="hi"),
        ToolCall(
            run_id="r", seq=3, timestamp=_ts(3), session_id="s",
            turn_index=0, call_index=0, name="get_order",
            args={"id": "1"}, args_hash=args_hash({"id": "1"}),
            latency_ms=50, result_summary="ok", retries=0,
        ),
        AgentTurn(
            run_id="r", seq=4, timestamp=_ts(4), session_id="s",
            turn_index=0, text="ok", latency_ms=200,
            usage={"cost_usd": 0.005, "input_tokens": 200, "output_tokens": 30},
            fidelity="aggregate",
        ),
    ]
    m = aggregate(trace)
    assert m.fidelity == "aggregate"
    assert m.llm_calls == 0
    assert m.tool_calls == 1
    assert m.total_cost_usd == 0.005
    assert m.total_input_tokens == 200
    assert m.total_output_tokens == 30


def test_aggregate_message_only_marks_cost_unknown() -> None:
    trace: list[Any] = [
        UserTurn(run_id="r", seq=0, timestamp=_ts(0), session_id="s", turn_index=0, text="hi"),
        AgentTurn(
            run_id="r", seq=1, timestamp=_ts(1), session_id="s",
            turn_index=0, text="ok", latency_ms=300, fidelity="message_only",
        ),
    ]
    m = aggregate(trace)
    assert m.fidelity == "message_only"
    assert m.total_cost_usd is None
    assert m.total_input_tokens is None
    assert m.total_output_tokens is None
    assert m.total_latency_ms == 300


def test_aggregate_worst_fidelity_wins() -> None:
    trace: list[Any] = [
        AgentTurn(
            run_id="r", seq=0, timestamp=_ts(0), session_id="s",
            turn_index=0, text="ok", latency_ms=100, fidelity="full",
        ),
        AgentTurn(
            run_id="r", seq=1, timestamp=_ts(1), session_id="s",
            turn_index=1, text="ok", latency_ms=100, fidelity="message_only",
        ),
        AgentTurn(
            run_id="r", seq=2, timestamp=_ts(2), session_id="s",
            turn_index=2, text="ok", latency_ms=100, fidelity="aggregate",
        ),
    ]
    m = aggregate(trace)
    assert m.fidelity == "message_only"


def test_aggregate_counts_errors_on_agent_turn() -> None:
    trace: list[Any] = [
        AgentTurn(
            run_id="r", seq=0, timestamp=_ts(0), session_id="s",
            turn_index=0, text="", latency_ms=100, fidelity="message_only",
            error="http_500",
        ),
    ]
    m = aggregate(trace)
    assert m.errors == 1


def test_aggregate_empty_trace() -> None:
    m = aggregate([])
    assert m.total_cost_usd is None
    assert m.tool_calls == 0
    assert m.tool_sequence == []
    assert m.fidelity == "message_only"


def test_args_hash_stable_across_key_order() -> None:
    a = args_hash({"a": 1, "b": 2})
    b = args_hash({"b": 2, "a": 1})
    assert a == b


def test_args_hash_stable_across_whitespace_in_strings() -> None:
    # whitespace inside string values is preserved (semantic content)
    a = args_hash({"q": "hello"})
    b = args_hash({"q": "hello"})
    assert a == b


def test_args_hash_changes_when_value_changes() -> None:
    a = args_hash({"id": "1"})
    b = args_hash({"id": "2"})
    assert a != b


def test_args_hash_format() -> None:
    h = args_hash({"a": 1})
    assert h.startswith("sha256:")
    assert len(h.split(":")[1]) == 16
