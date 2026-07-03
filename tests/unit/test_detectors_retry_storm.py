"""Tests for the retry-storm detector."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agentchaos.detectors.retry_storm import detect_retry_storms
from agentchaos.trace.schema import Retry, ToolCall, TraceEvent


def _tool(seq: int, name: str, retries: int = 0) -> ToolCall:
    return ToolCall(
        run_id="r",
        seq=seq,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        turn_index=0,
        call_index=seq,
        name=name,
        args={},
        args_hash="h",
        retries=retries,
    )


def _retry(seq: int) -> Retry:
    return Retry(
        run_id="r",
        seq=seq,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        turn_index=0,
        logical_call_index=0,
        attempt=1,
    )


def test_per_tool_storm_fires_high() -> None:
    trace: list[TraceEvent] = [
        _tool(0, "get_order", retries=6),  # >= 2 * threshold (3)
    ]
    findings = detect_retry_storms(trace, per_tool_threshold=3, aggregate_threshold=100)
    # Only per-tool fires (aggregate too high).
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == "high"
    assert f.evidence == {
        "scope": "per_tool",
        "tool": "get_order",
        "retries": 6,
        "threshold": 3,
    }


def test_per_tool_storm_fires_warn_at_threshold() -> None:
    trace: list[TraceEvent] = [
        _tool(0, "get_order", retries=3),
    ]
    findings = detect_retry_storms(trace, per_tool_threshold=3, aggregate_threshold=100)
    assert len(findings) == 1
    assert findings[0].severity == "warn"


def test_aggregate_storm_fires() -> None:
    trace: list[TraceEvent] = [
        _tool(0, "a", retries=4),
        _tool(1, "b", retries=4),
        _retry(2),
        _retry(3),
    ]
    findings = detect_retry_storms(
        trace, per_tool_threshold=10, aggregate_threshold=5
    )
    # No per-tool finding (threshold 10); one aggregate at retries=10 -> high.
    assert len(findings) == 1
    f = findings[0]
    assert f.evidence["scope"] == "aggregate"
    assert f.evidence["retries"] == 10
    assert f.severity == "high"


def test_retry_events_count_aggregate_only() -> None:
    trace: list[TraceEvent] = [
        _retry(0), _retry(1), _retry(2), _retry(3),
    ]
    findings = detect_retry_storms(
        trace, per_tool_threshold=3, aggregate_threshold=4
    )
    # No tool retries, so no per-tool finding. Aggregate fires.
    assert len(findings) == 1
    assert findings[0].evidence == {
        "scope": "aggregate",
        "retries": 4,
        "threshold": 4,
    }


def test_zero_retries_returns_empty() -> None:
    trace: list[TraceEvent] = [
        _tool(0, "get_order", retries=0),
        _tool(1, "create_label", retries=0),
    ]
    assert detect_retry_storms(trace) == []


def test_empty_trace_returns_empty() -> None:
    assert detect_retry_storms([]) == []


def test_invalid_thresholds_raise() -> None:
    with pytest.raises(ValueError):
        detect_retry_storms([], per_tool_threshold=0)
    with pytest.raises(ValueError):
        detect_retry_storms([], aggregate_threshold=0)


def test_per_tool_sorted_deterministically() -> None:
    trace: list[TraceEvent] = [
        _tool(0, "z_tool", retries=5),
        _tool(1, "a_tool", retries=5),
    ]
    findings = detect_retry_storms(
        trace, per_tool_threshold=3, aggregate_threshold=100
    )
    # Sorted by tool name.
    tools = [f.evidence["tool"] for f in findings if f.evidence["scope"] == "per_tool"]
    assert tools == ["a_tool", "z_tool"]
