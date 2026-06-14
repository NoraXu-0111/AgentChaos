"""Combine expectation checks, budget checks, and regression checks into a Verdict."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict

from agentchaos.budget.check import check_absolute, check_detectors, check_regression
from agentchaos.budget.schema import Budget
from agentchaos.chaos.policy import ChaosPolicy
from agentchaos.detectors.schema import Finding
from agentchaos.profile.compare import Diff
from agentchaos.profile.metrics import Metrics
from agentchaos.scenario.schema import Expectation
from agentchaos.trace.schema import AgentTurn, ChaosInjected, TraceEvent
from agentchaos.violations import Violation

# Exit codes per v0 plan.
EXIT_PASS = 0
EXIT_USAGE_ERROR = 1
EXIT_BUDGET_OR_EXPECTATION_FAIL = 2
EXIT_CHAOS_FAIL = 3
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


def check_chaos_expectations(
    chaos: ChaosPolicy | None,
    trace: Iterable[TraceEvent],
    session_error: str | None,
) -> list[Violation]:
    """Return chaos-related Violations.

    When ``expect_fallback`` is set and chaos was actually injected, the agent
    must degrade gracefully. Two signals indicate it did NOT:

    - a transport-level ``session_error`` (the agent crashed outright), or
    - an ``AgentTurn`` that surfaced an ``error`` to the user instead of a
      recovered, fallback response.
    """
    if chaos is None:
        return []

    trace_events = list(trace)
    injected = [e for e in trace_events if isinstance(e, ChaosInjected)]
    if not (chaos.expect_fallback and injected):
        return []

    agent_errors = [
        e for e in trace_events if isinstance(e, AgentTurn) and e.error is not None
    ]
    if session_error is None and not agent_errors:
        return []

    detail = session_error or (agent_errors[0].error if agent_errors else "agent error")
    return [
        Violation(
            kind="chaos",
            name="expect_fallback",
            detail=(
                "chaos was injected but the agent failed instead of taking a "
                f"fallback path: {detail}"
            ),
        )
    ]


def compute_verdict(
    metrics: Metrics,
    expectation: Expectation,
    budget: Budget,
    *,
    diff: Diff | None = None,
    final_text: str = "",
    session_error: str | None = None,
    findings: list[Finding] | None = None,
    chaos: ChaosPolicy | None = None,
    trace: Iterable[TraceEvent] | None = None,
) -> Verdict:
    """Combine all checks into a Verdict.

    Precedence: a transport-level session error (exit 4) short-circuits
    everything. Otherwise chaos failures (exit 3) dominate budget/expectation
    failures (exit 2).
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

    trace_list = list(trace) if trace is not None else []
    chaos_violations = check_chaos_expectations(chaos, trace_list, session_error)

    other_violations: list[Violation] = []
    other_violations.extend(check_expectations(expectation, metrics, final_text))
    other_violations.extend(check_absolute(metrics, budget))
    if diff is not None:
        other_violations.extend(check_regression(diff.delta_pct_map(), budget))
    other_violations.extend(check_detectors(findings or [], budget))

    violations = chaos_violations + other_violations
    if not violations:
        return Verdict(outcome="pass", violations=violations, exit_code=EXIT_PASS)

    exit_code = EXIT_CHAOS_FAIL if chaos_violations else EXIT_BUDGET_OR_EXPECTATION_FAIL
    outcome: Literal["pass", "fail"] = "fail"
    return Verdict(outcome=outcome, violations=violations, exit_code=exit_code)
