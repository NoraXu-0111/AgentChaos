"""Tests for budget schema and absolute/regression checks."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentchaos.budget import Budget, check_absolute, check_regression
from agentchaos.profile.metrics import Metrics


def test_budget_accepts_all_v0_fields() -> None:
    b = Budget(
        max_cost_usd=0.05,
        max_total_latency_ms=8000,
        max_turn_latency_ms=5000,
        max_tool_calls=8,
        max_llm_calls=5,
        max_retries=2,
        max_input_tokens=8000,
        max_cost_regression_pct=20,
        max_latency_regression_pct=30,
        max_tool_call_regression_pct=50,
        max_input_token_regression_pct=50,
    )
    assert b.max_cost_usd == 0.05
    assert b.max_input_token_regression_pct == 50


def test_budget_rejects_negative() -> None:
    with pytest.raises(ValidationError):
        Budget(max_cost_usd=-1)


def test_budget_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Budget(unknown_field=1)  # type: ignore[call-arg]


def test_check_absolute_pass_when_within_limits() -> None:
    metrics = Metrics(total_cost_usd=0.01, total_latency_ms=1000, tool_calls=1)
    budget = Budget(max_cost_usd=0.05, max_total_latency_ms=8000, max_tool_calls=5)
    assert check_absolute(metrics, budget) == []


def test_check_absolute_cost_violation() -> None:
    metrics = Metrics(total_cost_usd=0.10)
    budget = Budget(max_cost_usd=0.05)
    violations = check_absolute(metrics, budget)
    assert len(violations) == 1
    assert violations[0].name == "max_cost_usd"
    assert violations[0].kind == "budget"
    assert "0.10" in violations[0].detail or "0.1000" in violations[0].detail


def test_check_absolute_multiple_violations() -> None:
    metrics = Metrics(
        total_cost_usd=0.10,
        total_latency_ms=10000,
        max_turn_latency_ms=6000,
        tool_calls=20,
        llm_calls=10,
        retries=5,
        total_input_tokens=20000,
    )
    budget = Budget(
        max_cost_usd=0.05,
        max_total_latency_ms=8000,
        max_turn_latency_ms=5000,
        max_tool_calls=8,
        max_llm_calls=5,
        max_retries=2,
        max_input_tokens=8000,
    )
    violations = check_absolute(metrics, budget)
    names = {v.name for v in violations}
    assert names == {
        "max_cost_usd",
        "max_total_latency_ms",
        "max_turn_latency_ms",
        "max_tool_calls",
        "max_llm_calls",
        "max_retries",
        "max_input_tokens",
    }


def test_check_absolute_skips_unset_budget() -> None:
    metrics = Metrics(total_cost_usd=999.0)
    budget = Budget()  # all None
    assert check_absolute(metrics, budget) == []


def test_check_absolute_skips_unset_metric() -> None:
    metrics = Metrics(total_cost_usd=None)
    budget = Budget(max_cost_usd=0.05)
    assert check_absolute(metrics, budget) == []


def test_check_regression_pass_when_within_limits() -> None:
    deltas = {"total_cost_usd": 10.0, "total_latency_ms": 5.0}
    budget = Budget(max_cost_regression_pct=20, max_latency_regression_pct=30)
    assert check_regression(deltas, budget) == []


def test_check_regression_cost_violation() -> None:
    deltas = {"total_cost_usd": 42.0}
    budget = Budget(max_cost_regression_pct=20)
    violations = check_regression(deltas, budget)
    assert len(violations) == 1
    assert violations[0].kind == "regression_budget"
    assert violations[0].name == "max_cost_regression_pct"
    assert "42" in violations[0].detail
    assert "20" in violations[0].detail


def test_check_regression_negative_delta_does_not_violate() -> None:
    deltas = {"total_cost_usd": -50.0}
    budget = Budget(max_cost_regression_pct=20)
    assert check_regression(deltas, budget) == []


def test_check_regression_only_when_budget_set() -> None:
    deltas = {"total_cost_usd": 999.0}
    budget = Budget()  # no regression budgets
    assert check_regression(deltas, budget) == []


def test_check_regression_only_when_delta_present() -> None:
    deltas: dict[str, float] = {}
    budget = Budget(max_cost_regression_pct=20)
    assert check_regression(deltas, budget) == []
