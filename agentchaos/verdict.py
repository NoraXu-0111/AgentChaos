"""Combine expectation checks, budget checks, and regression checks into a Verdict."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from agentchaos.budget.check import check_absolute, check_detectors, check_regression
from agentchaos.budget.schema import Budget
from agentchaos.detectors.schema import Finding
from agentchaos.profile.compare import Diff
from agentchaos.profile.metrics import Metrics
from agentchaos.scenario.schema import Expectation
from agentchaos.violations import Violation

# Exit codes per v0 plan.
EXIT_PASS = 0
EXIT_USAGE_ERROR = 1
EXIT_BUDGET_OR_EXPECTATION_FAIL = 2
EXIT_TRANSPORT_FAIL = 4


class Verdict(BaseModel):
    """Final outcome of a run."""

    model_config = ConfigDict(extra="forbid")

    outcome: Literal["pass", "fail"]
    violations: list[Violation]
    exit_code: int


def check_expectations(
    expectation: Expectation,
    metrics: Metrics,
    final_text: str = "",
) -> list[Violation]:
    """Return one Violation per expectation breach."""
    violations: list[Violation] = []
    by_tool = metrics.by_tool

    for tool in expectation.must_call_tools:
        if tool not in by_tool:
            violations.append(
                Violation(
                    kind="expectation",
                    name="must_call_tools",
                    detail=f"tool '{tool}' was not called",
                )
            )

    for tool in expectation.must_not_call_tools:
        if tool in by_tool:
            violations.append(
                Violation(
                    kind="expectation",
                    name="must_not_call_tools",
                    detail=f"tool '{tool}' was called but should not have been",
                )
            )

    for needle in expectation.final_response_contains:
        if needle.lower() not in final_text.lower():
            violations.append(
                Violation(
                    kind="expectation",
                    name="final_response_contains",
                    detail=f"final response did not contain {needle!r}",
                )
            )

    for needle in expectation.final_response_not_contains:
        if needle.lower() in final_text.lower():
            violations.append(
                Violation(
                    kind="expectation",
                    name="final_response_not_contains",
                    detail=f"final response contained {needle!r} but should not have",
                )
            )

    return violations


def compute_verdict(
    metrics: Metrics,
    expectation: Expectation,
    budget: Budget,
    *,
    diff: Diff | None = None,
    final_text: str = "",
    session_error: str | None = None,
    findings: list[Finding] | None = None,
) -> Verdict:
    """Combine all checks into a Verdict.

    Transport-level session errors map to exit 4 and short-circuit the rest of
    the checks — no point asserting expectations on a half-run conversation.
    """
    if session_error is not None:
        return Verdict(
            outcome="fail",
            violations=[
                Violation(
                    kind="expectation",
                    name="transport_error",
                    detail=session_error,
                ),
            ],
            exit_code=EXIT_TRANSPORT_FAIL,
        )

    violations: list[Violation] = []
    violations.extend(check_expectations(expectation, metrics, final_text))
    violations.extend(check_absolute(metrics, budget))
    if diff is not None:
        violations.extend(check_regression(diff.delta_pct_map(), budget))
    violations.extend(check_detectors(findings or [], budget))

    outcome: Literal["pass", "fail"] = "fail" if violations else "pass"
    exit_code = EXIT_BUDGET_OR_EXPECTATION_FAIL if violations else EXIT_PASS
    return Verdict(outcome=outcome, violations=violations, exit_code=exit_code)
