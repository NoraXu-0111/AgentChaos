"""Tests for compute_verdict and expectation checks."""
from __future__ import annotations

from datetime import UTC, datetime

from agentchaos.budget.schema import Budget
from agentchaos.chaos.policy import ChaosPolicy, ChaosTarget, ToolChaosPolicy
from agentchaos.detectors.schema import Finding
from agentchaos.profile.compare import diff
from agentchaos.profile.metrics import Metrics
from agentchaos.scenario.schema import Expectation
from agentchaos.trace.schema import AgentTurn, ChaosInjected
from agentchaos.verdict import (
    EXIT_BUDGET_OR_EXPECTATION_FAIL,
    EXIT_CHAOS_FAIL,
    EXIT_PASS,
    EXIT_TRANSPORT_FAIL,
    check_chaos_expectations,
    check_expectations,
    compute_verdict,
)


def _chaos_event() -> ChaosInjected:
    return ChaosInjected(
        run_id="r",
        seq=1,
        timestamp=datetime.now(UTC),
        target="get_order",
        policy="failure_rate=1.0 status_code=503",
        injection_type="status_code",
        value=503,
        tool_name="get_order",
    )


def _chaos_policy() -> ChaosPolicy:
    return ChaosPolicy(
        expect_fallback=True,
        targets=[ChaosTarget(tool="get_order",
                             policy=ToolChaosPolicy(failure_rate=1.0, status_code=503))],
    )


def _agent_error_turn() -> AgentTurn:
    return AgentTurn(
        run_id="r",
        seq=2,
        timestamp=datetime.now(UTC),
        turn_index=0,
        text="",
        latency_ms=5,
        error="agent blew up on tool error",
    )


def test_verdict_pass_on_clean_run() -> None:
    metrics = Metrics(total_cost_usd=0.01, by_tool={"get_order": 1})
    v = compute_verdict(
        metrics,
        Expectation(must_call_tools=["get_order"], final_response_contains=["refund"]),
        Budget(max_cost_usd=0.05),
        final_text="here is your refund",
    )
    assert v.outcome == "pass"
    assert v.exit_code == EXIT_PASS
    assert v.violations == []


def test_must_call_tool_missing() -> None:
    metrics = Metrics(by_tool={"create_label": 1})
    v = compute_verdict(
        metrics,
        Expectation(must_call_tools=["get_order"]),
        Budget(),
    )
    assert v.outcome == "fail"
    assert v.exit_code == EXIT_BUDGET_OR_EXPECTATION_FAIL
    assert any(x.name == "must_call_tools" for x in v.violations)


def test_must_not_call_tool_called() -> None:
    metrics = Metrics(by_tool={"delete_customer": 1})
    v = compute_verdict(
        metrics,
        Expectation(must_not_call_tools=["delete_customer"]),
        Budget(),
    )
    assert any(x.name == "must_not_call_tools" for x in v.violations)


def test_final_response_contains() -> None:
    v = compute_verdict(
        Metrics(),
        Expectation(final_response_contains=["refund"]),
        Budget(),
        final_text="hello world",
    )
    assert any(x.name == "final_response_contains" for x in v.violations)


def test_final_response_not_contains() -> None:
    v = compute_verdict(
        Metrics(),
        Expectation(final_response_not_contains=["I cannot help"]),
        Budget(),
        final_text="Sorry, I cannot help you with that.",
    )
    assert any(x.name == "final_response_not_contains" for x in v.violations)


def test_absolute_budget_violation() -> None:
    v = compute_verdict(
        Metrics(total_cost_usd=0.10),
        Expectation(),
        Budget(max_cost_usd=0.05),
    )
    assert v.outcome == "fail"
    assert any(x.kind == "budget" for x in v.violations)


def test_regression_budget_violation_with_diff() -> None:
    b = Metrics(total_cost_usd=0.001)
    c = Metrics(total_cost_usd=0.002)
    v = compute_verdict(
        c,
        Expectation(),
        Budget(max_cost_regression_pct=20),
        diff=diff(b, c),
    )
    assert any(x.kind == "regression_budget" for x in v.violations)


def test_regression_budget_skipped_when_no_diff() -> None:
    v = compute_verdict(
        Metrics(total_cost_usd=999),
        Expectation(),
        Budget(max_cost_regression_pct=1),  # would fail if a diff was provided
        diff=None,
    )
    assert v.outcome == "pass"


def test_session_error_short_circuits() -> None:
    v = compute_verdict(
        Metrics(),
        Expectation(must_call_tools=["any"]),
        Budget(max_cost_usd=0.01),
        session_error="timeout",
    )
    assert v.outcome == "fail"
    assert v.exit_code == EXIT_TRANSPORT_FAIL
    # No budget/expectation violations should appear; only the transport_error one.
    assert len(v.violations) == 1
    assert v.violations[0].name == "transport_error"


def test_check_expectations_case_insensitive_contains() -> None:
    violations = check_expectations(
        Expectation(final_response_contains=["Refund"]),
        Metrics(),
        final_text="here is your refund label",
    )
    assert violations == []


def test_findings_with_matching_budget_emit_violation_and_exit_2() -> None:
    finding = Finding(
        detector="loop",
        severity="high",
        description="repeated tool",
        evidence={"tool": "x"},
    )
    v = compute_verdict(
        Metrics(),
        Expectation(),
        Budget(max_loop_repetitions=3),
        findings=[finding],
    )
    assert v.outcome == "fail"
    assert v.exit_code == EXIT_BUDGET_OR_EXPECTATION_FAIL
    assert any(x.kind == "detector" for x in v.violations)


def test_findings_without_budget_no_violation() -> None:
    finding = Finding(
        detector="loop",
        severity="high",
        description="repeated tool",
        evidence={"tool": "x"},
    )
    v = compute_verdict(
        Metrics(),
        Expectation(),
        Budget(),  # no detector budget
        findings=[finding],
    )
    assert v.outcome == "pass"
    assert v.violations == []


def test_transport_error_still_wins_over_detectors() -> None:
    finding = Finding(
        detector="loop",
        severity="high",
        description="repeated tool",
        evidence={"tool": "x"},
    )
    v = compute_verdict(
        Metrics(),
        Expectation(),
        Budget(max_loop_repetitions=3),
        findings=[finding],
        session_error="boom",
    )
    assert v.exit_code == EXIT_TRANSPORT_FAIL
    # Only the transport error, not the detector violation.
    assert len(v.violations) == 1
    assert v.violations[0].name == "transport_error"


def test_chaos_none_returns_empty() -> None:
    assert check_chaos_expectations(None, [_chaos_event()], None) == []
    assert check_chaos_expectations(None, [_chaos_event()], "boom") == []


def test_chaos_clean_run_no_violation() -> None:
    # Chaos injected, agent recovered (no agent error, no session error) → pass.
    assert check_chaos_expectations(_chaos_policy(), [_chaos_event()], None) == []


def test_chaos_fail_sets_exit_3() -> None:
    # Chaos injected + expect_fallback + an agent error turn (no transport error).
    v = compute_verdict(
        Metrics(),
        Expectation(),
        Budget(),
        chaos=_chaos_policy(),
        trace=[_chaos_event(), _agent_error_turn()],
        session_error=None,
    )
    assert v.outcome == "fail"
    assert v.exit_code == EXIT_CHAOS_FAIL
    assert any(x.kind == "chaos" for x in v.violations)


def test_chaos_dominates_budget() -> None:
    # A chaos violation AND a budget violation → exit 3, not 2.
    v = compute_verdict(
        Metrics(total_cost_usd=999),
        Expectation(),
        Budget(max_cost_usd=0.01),
        chaos=_chaos_policy(),
        trace=[_chaos_event(), _agent_error_turn()],
        session_error=None,
    )
    assert v.exit_code == EXIT_CHAOS_FAIL
    kinds = {x.kind for x in v.violations}
    assert "chaos" in kinds and "budget" in kinds


def test_transport_error_wins_over_chaos() -> None:
    v = compute_verdict(
        Metrics(),
        Expectation(),
        Budget(),
        chaos=_chaos_policy(),
        trace=[_chaos_event()],
        session_error="http_503",
    )
    assert v.exit_code == EXIT_TRANSPORT_FAIL
    assert len(v.violations) == 1
    assert v.violations[0].name == "transport_error"


def test_violations_aggregated_in_order() -> None:
    metrics = Metrics(
        total_cost_usd=0.10,
        tool_calls=10,
        by_tool={"create_label": 1},
    )
    v = compute_verdict(
        metrics,
        Expectation(must_call_tools=["get_order"]),
        Budget(max_cost_usd=0.05, max_tool_calls=8),
    )
    kinds = [x.kind for x in v.violations]
    # Expectations come first.
    assert kinds[0] == "expectation"
    assert "budget" in kinds
