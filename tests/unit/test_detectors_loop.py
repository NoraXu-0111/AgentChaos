"""Tests for the loop detector."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agentchaos.detectors.loop import detect_loops
from agentchaos.trace.schema import ToolCall, TraceEvent


def _tool(seq: int, name: str, args_hash: str) -> ToolCall:
    return ToolCall(
        run_id="r",
        seq=seq,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        turn_index=0,
        call_index=seq,
        name=name,
        args={},
        args_hash=args_hash,
    )


def test_threshold_met_emits_high_when_count_exceeds() -> None:
    trace: list[TraceEvent] = [
        _tool(0, "get_order", "h1"),
        _tool(1, "get_order", "h1"),
        _tool(2, "get_order", "h1"),
        _tool(3, "get_order", "h1"),
        _tool(4, "other", "z"),
    ]
    findings = detect_loops(trace, window=5, threshold=3)
    assert len(findings) == 1
    f = findings[0]
    assert f.detector == "loop"
    assert f.severity == "high"
    assert f.evidence["count"] == 4
    assert f.evidence["tool"] == "get_order"
    assert f.evidence["first_seq"] == 0
    assert f.evidence["last_seq"] == 3


def test_threshold_met_exactly_emits_warn() -> None:
    trace: list[TraceEvent] = [
        _tool(0, "get_order", "h1"),
        _tool(1, "get_order", "h1"),
        _tool(2, "get_order", "h1"),
        _tool(3, "other", "z"),
        _tool(4, "other", "z"),
    ]
    findings = detect_loops(trace, window=5, threshold=3)
    assert len(findings) == 1
    assert findings[0].severity == "warn"
    assert findings[0].evidence["count"] == 3


def test_below_threshold_returns_empty() -> None:
    trace: list[TraceEvent] = [
        _tool(0, "get_order", "h1"),
        _tool(1, "get_order", "h1"),
        _tool(2, "other", "z"),
    ]
    assert detect_loops(trace, window=5, threshold=3) == []


def test_widely_spaced_calls_do_not_trigger() -> None:
    # 3 calls but they sit at positions 0, 5, 10 — never inside a window of 4.
    trace: list[TraceEvent] = [
        _tool(0, "get_order", "h1"),
        _tool(1, "a", "x"), _tool(2, "b", "x"), _tool(3, "c", "x"), _tool(4, "d", "x"),
        _tool(5, "get_order", "h1"),
        _tool(6, "a", "x"), _tool(7, "b", "x"), _tool(8, "c", "x"), _tool(9, "d", "x"),
        _tool(10, "get_order", "h1"),
    ]
    assert detect_loops(trace, window=4, threshold=3) == []


def test_short_trace_falls_back_to_full_scan() -> None:
    # Only 3 tool calls but we ask for a window of 5 — uses the whole list.
    trace: list[TraceEvent] = [
        _tool(0, "get_order", "h1"),
        _tool(1, "get_order", "h1"),
        _tool(2, "get_order", "h1"),
    ]
    findings = detect_loops(trace, window=5, threshold=3)
    assert len(findings) == 1
    assert findings[0].evidence["window"] == 3
    assert findings[0].evidence["count"] == 3


def test_empty_trace_returns_empty() -> None:
    assert detect_loops([], window=5, threshold=3) == []


def test_invalid_window_raises() -> None:
    with pytest.raises(ValueError):
        detect_loops([], window=0, threshold=3)


def test_invalid_threshold_raises() -> None:
    with pytest.raises(ValueError):
        detect_loops([], window=5, threshold=1)


def test_dedupe_keeps_strongest_finding_across_windows() -> None:
    # Window 1 (indexes 0..4) has count=4 of (x, h); window 2 (1..5) has count=3.
    # The first window finds the bigger count; later windows must NOT downgrade it.
    trace: list[TraceEvent] = [
        _tool(0, "x", "h"),
        _tool(1, "x", "h"),
        _tool(2, "x", "h"),
        _tool(3, "x", "h"),
        _tool(4, "y", "z"),
        _tool(5, "y", "z"),
    ]
    findings = detect_loops(trace, window=5, threshold=3)
    # The (x, h) finding should remain at the high count of 4.
    f = next(f for f in findings if f.evidence["tool"] == "x")
    assert f.evidence["count"] == 4
    assert f.severity == "high"


def test_collision_keyed_by_tool_and_args_hash() -> None:
    # Different tools share the same args_hash; must NOT be merged.
    trace: list[TraceEvent] = [
        _tool(0, "a", "h"),
        _tool(1, "a", "h"),
        _tool(2, "b", "h"),
        _tool(3, "b", "h"),
        _tool(4, "b", "h"),
    ]
    findings = detect_loops(trace, window=5, threshold=3)
    # Only "b" hits the threshold (3); "a" stops at 2.
    assert len(findings) == 1
    assert findings[0].evidence["tool"] == "b"
