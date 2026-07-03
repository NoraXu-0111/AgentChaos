"""Integration tests covering aggregate → run_detectors → compute_verdict.

Synthetic traces drive the gating logic without any I/O.
"""
from __future__ import annotations

from datetime import UTC, datetime

from agentchaos.budget.schema import Budget
from agentchaos.detectors.runner import run_detectors
from agentchaos.profile.metrics import aggregate
from agentchaos.scenario.schema import Expectation
from agentchaos.trace.schema import ModelCall, ToolCall, TraceEvent
from agentchaos.verdict import (
    EXIT_BUDGET_OR_EXPECTATION_FAIL,
    EXIT_PASS,
    compute_verdict,
)


def _tc(seq: int, name: str, args_hash: str) -> ToolCall:
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


def _mc(seq: int, cost: float) -> ModelCall:
    return ModelCall(
        run_id="r",
        seq=seq,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        turn_index=0,
        call_index=seq,
        model="gpt-4o-mini",
        cost_usd=cost,
        input_tokens=100,
    )


def test_loop_with_budget_fails_exit_2() -> None:
    trace: list[TraceEvent] = [
        _tc(0, "get_order", "h"),
        _tc(1, "get_order", "h"),
        _tc(2, "get_order", "h"),
        _tc(3, "get_order", "h"),
    ]
    metrics = aggregate(trace)
    findings = run_detectors(trace, Budget(max_loop_repetitions=3))
    verdict = compute_verdict(
        metrics,
        Expectation(),
        Budget(max_loop_repetitions=3),
        findings=findings,
    )
    assert verdict.outcome == "fail"
    assert verdict.exit_code == EXIT_BUDGET_OR_EXPECTATION_FAIL
    assert any(v.kind == "detector" and v.name == "max_loop_repetitions"
               for v in verdict.violations)


def test_loop_without_budget_passes() -> None:
    trace: list[TraceEvent] = [
        _tc(0, "get_order", "h"),
        _tc(1, "get_order", "h"),
        _tc(2, "get_order", "h"),
        _tc(3, "get_order", "h"),
    ]
    metrics = aggregate(trace)
    findings = run_detectors(trace, Budget())  # no detector budgets
    verdict = compute_verdict(
        metrics,
        Expectation(),
        Budget(),
        findings=findings,
    )
    # Findings still produced, but no violation → pass.
    assert verdict.outcome == "pass"
    assert verdict.exit_code == EXIT_PASS
    assert any(f.detector == "loop" for f in findings)


def test_cost_explosion_with_budget_fails() -> None:
    trace: list[TraceEvent] = [
        _mc(0, 0.001),
        _mc(1, 0.001),
        _mc(2, 0.001),
        _mc(3, 0.030),
    ]
    metrics = aggregate(trace)
    budget = Budget(max_cost_explosion_factor=5.0)
    findings = run_detectors(trace, budget)
    verdict = compute_verdict(
        metrics,
        Expectation(),
        budget,
        findings=findings,
    )
    assert verdict.outcome == "fail"
    assert any(v.name == "max_cost_explosion_factor" for v in verdict.violations)
