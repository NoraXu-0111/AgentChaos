"""Tests for run_detectors orchestration."""
from __future__ import annotations

from datetime import UTC, datetime

from agentchaos.budget.schema import Budget
from agentchaos.detectors.runner import run_detectors
from agentchaos.trace.schema import ModelCall, Retry, ToolCall, TraceEvent


def _tc(
    seq: int,
    name: str,
    args_hash: str,
    *,
    retries: int = 0,
    turn: int = 0,
) -> ToolCall:
    return ToolCall(
        run_id="r",
        seq=seq,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        turn_index=turn,
        call_index=seq,
        name=name,
        args={},
        args_hash=args_hash,
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


def _mc(seq: int, cost: float, *, turn: int = 0, tokens: int = 100) -> ModelCall:
    return ModelCall(
        run_id="r",
        seq=seq,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        turn_index=turn,
        call_index=seq,
        model="gpt-4o-mini",
        cost_usd=cost,
        input_tokens=tokens,
    )


def test_collects_all_three_detectors() -> None:
    trace: list[TraceEvent] = [
        # Loop
        _tc(0, "get_order", "h", retries=4),  # also a per-tool retry storm
        _tc(1, "get_order", "h", retries=0),
        _tc(2, "get_order", "h", retries=0),
        _tc(3, "get_order", "h", retries=0),
        # Cost explosion
        _mc(4, 0.001),
        _mc(5, 0.001),
        _mc(6, 0.030),
    ]
    findings = run_detectors(trace, budget=None)
    detectors = {f.detector for f in findings}
    assert detectors == {"loop", "retry_storm", "cost_explosion"}


def test_respects_budget_overrides() -> None:
    # With default loop_threshold=3 this would fire. Push it to 5 so it doesn't.
    trace: list[TraceEvent] = [
        _tc(0, "get_order", "h"),
        _tc(1, "get_order", "h"),
        _tc(2, "get_order", "h"),
        _tc(3, "get_order", "h"),
    ]
    findings = run_detectors(
        trace, budget=Budget(max_loop_repetitions=5, loop_window=5)
    )
    assert findings == []


def test_uses_defaults_when_budget_is_none() -> None:
    trace: list[TraceEvent] = [
        _tc(0, "get_order", "h"),
        _tc(1, "get_order", "h"),
        _tc(2, "get_order", "h"),
        _tc(3, "get_order", "h"),
    ]
    findings = run_detectors(trace, budget=None)
    assert any(f.detector == "loop" for f in findings)


def test_sorted_by_severity_then_detector() -> None:
    # Construct a trace that fires both a high cost_explosion and a warn loop.
    trace: list[TraceEvent] = [
        _tc(0, "x", "a"),
        _tc(1, "x", "a"),
        _tc(2, "x", "a"),  # warn loop (count == threshold)
        _mc(3, 0.001),
        _mc(4, 0.001),
        _mc(5, 0.001),
        _mc(6, 0.050),  # high cost explosion
        _retry(7),
    ]
    findings = run_detectors(trace, budget=None)
    severities = [f.severity for f in findings]
    # high first
    assert severities[0] == "high"
    # any subsequent severities must be >= "high" in rank
    ranks = [{"high": 0, "warn": 1, "info": 2}[s] for s in severities]
    assert ranks == sorted(ranks)


def test_accepts_generator_input() -> None:
    def gen() -> list[TraceEvent]:
        return [
            _tc(0, "get_order", "h"),
            _tc(1, "get_order", "h"),
            _tc(2, "get_order", "h"),
        ]

    findings = run_detectors(iter(gen()), budget=None)
    assert any(f.detector == "loop" for f in findings)
