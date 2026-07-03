"""Tests for the cost-explosion detector."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agentchaos.detectors.cost_explosion import detect_cost_explosions
from agentchaos.trace.schema import ModelCall, ToolCall, TraceEvent


def _mc(
    seq: int,
    *,
    cost_usd: float | None,
    model: str = "gpt-4o-mini",
    turn: int = 0,
    input_tokens: int | None = None,
    name: str | None = None,
) -> ModelCall:
    return ModelCall(
        run_id="r",
        seq=seq,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        turn_index=turn,
        call_index=seq,
        name=name,
        model=model,
        cost_usd=cost_usd,
        input_tokens=input_tokens,
    )


def _tc(seq: int, name: str, args_hash: str, turn: int = 0) -> ToolCall:
    return ToolCall(
        run_id="r",
        seq=seq,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        turn_index=turn,
        call_index=seq,
        name=name,
        args={},
        args_hash=args_hash,
    )


def test_outlier_fires_high() -> None:
    trace: list[TraceEvent] = [
        _mc(0, cost_usd=0.001),
        _mc(1, cost_usd=0.001),
        _mc(2, cost_usd=0.001),
        _mc(3, cost_usd=0.020),  # 20x the median
    ]
    findings = detect_cost_explosions(trace, factor_threshold=5.0)
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == "high"
    assert f.evidence["cost_usd"] == 0.020
    assert f.evidence["median_cost_usd"] == 0.001
    assert f.evidence["factor"] == 20.0


def test_uniform_costs_return_empty() -> None:
    trace: list[TraceEvent] = [
        _mc(0, cost_usd=0.01),
        _mc(1, cost_usd=0.01),
        _mc(2, cost_usd=0.01),
    ]
    assert detect_cost_explosions(trace, factor_threshold=5.0) == []


def test_none_cost_skipped() -> None:
    trace: list[TraceEvent] = [
        _mc(0, cost_usd=None),
        _mc(1, cost_usd=None),
        _mc(2, cost_usd=0.05),
    ]
    # Only 1 valid call → fewer than 2 → empty.
    assert detect_cost_explosions(trace, factor_threshold=5.0) == []


def test_driver_input_tokens_identified() -> None:
    trace: list[TraceEvent] = [
        _mc(0, cost_usd=0.001, input_tokens=100),
        _mc(1, cost_usd=0.001, input_tokens=110),
        _mc(2, cost_usd=0.001, input_tokens=90),
        _mc(3, cost_usd=0.030, input_tokens=2000),
    ]
    findings = detect_cost_explosions(trace, factor_threshold=5.0)
    assert len(findings) == 1
    f = findings[0]
    assert f.evidence["driver"] == "input_tokens"
    assert f.evidence["driver_evidence"]["input_tokens"] == 2000


def test_driver_repeated_tool_call_identified() -> None:
    trace: list[TraceEvent] = [
        _mc(0, cost_usd=0.001, turn=0),
        _mc(1, cost_usd=0.001, turn=1),
        _mc(2, cost_usd=0.001, turn=2),
        _tc(3, "get_order", "h1", turn=3),
        _tc(4, "get_order", "h1", turn=3),
        _tc(5, "get_order", "h1", turn=3),
        _tc(6, "get_order", "h1", turn=3),
        _mc(7, cost_usd=0.030, turn=3, input_tokens=100),
    ]
    findings = detect_cost_explosions(trace, factor_threshold=5.0)
    assert len(findings) == 1
    ev = findings[0].evidence
    assert ev["driver"] == "repeated_tool_call"
    assert ev["driver_evidence"]["tool"] == "get_order"
    assert ev["driver_evidence"]["count"] == 4


def test_driver_unknown_when_no_signal() -> None:
    trace: list[TraceEvent] = [
        _mc(0, cost_usd=0.001, input_tokens=100),
        _mc(1, cost_usd=0.001, input_tokens=100),
        _mc(2, cost_usd=0.001, input_tokens=100),
        _mc(3, cost_usd=0.030, input_tokens=100),  # similar tokens → not the driver
    ]
    findings = detect_cost_explosions(trace, factor_threshold=5.0)
    assert len(findings) == 1
    assert findings[0].evidence["driver"] == "unknown"


def test_min_baseline_usd_floor() -> None:
    # All costs are below the min_baseline floor → no findings.
    trace: list[TraceEvent] = [
        _mc(0, cost_usd=0.00001),
        _mc(1, cost_usd=0.00001),
        _mc(2, cost_usd=0.001),
    ]
    findings = detect_cost_explosions(
        trace, factor_threshold=5.0, min_baseline_usd=0.0001
    )
    # Median of others (when 0.001 is candidate) = 0.00001 < floor; skipped.
    assert findings == []


def test_single_or_empty_returns_empty() -> None:
    assert detect_cost_explosions([], factor_threshold=5.0) == []
    assert detect_cost_explosions([_mc(0, cost_usd=0.1)], factor_threshold=5.0) == []


def test_invalid_factor_raises() -> None:
    with pytest.raises(ValueError):
        detect_cost_explosions([], factor_threshold=1.0)


def test_invalid_min_baseline_raises() -> None:
    with pytest.raises(ValueError):
        detect_cost_explosions([], min_baseline_usd=-0.01)
