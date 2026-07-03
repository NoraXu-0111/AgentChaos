"""Tests for compute_verdict and expectation checks."""
from __future__ import annotations

from agentchaos.budget.schema import Budget
from agentchaos.detectors.schema import Finding
from agentchaos.profile.compare import diff
from agentchaos.profile.metrics import Metrics
from agentchaos.scenario.schema import Expectation
from agentchaos.verdict import (
    EXIT_BUDGET_OR_EXPECTATION_FAIL,
    EXIT_PASS,
    EXIT_TRANSPORT_FAIL,
    check_expectations,
    compute_verdict,
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
