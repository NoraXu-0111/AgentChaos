"""Orchestrate all detectors and apply budget-driven threshold overrides."""
from __future__ import annotations

from collections.abc import Iterable

from agentchaos.budget.schema import Budget
from agentchaos.detectors.cost_explosion import detect_cost_explosions
from agentchaos.detectors.loop import detect_loops
from agentchaos.detectors.retry_storm import detect_retry_storms
from agentchaos.detectors.schema import Finding, Severity
from agentchaos.trace.schema import TraceEvent

DEFAULT_LOOP_WINDOW = 5
DEFAULT_LOOP_THRESHOLD = 3
DEFAULT_RETRY_PER_TOOL = 3
DEFAULT_RETRY_AGGREGATE = 6
DEFAULT_COST_FACTOR = 5.0
DEFAULT_COST_MIN_BASELINE_USD = 0.0001

_SEVERITY_ORDER: dict[Severity, int] = {"high": 0, "warn": 1, "info": 2}


def run_detectors(
    trace: Iterable[TraceEvent],
    budget: Budget | None = None,
) -> list[Finding]:
    """Run every detector and return findings sorted by severity, then name."""
    materialized: list[TraceEvent] = list(trace)

    loop_window = (
        budget.loop_window if budget is not None and budget.loop_window is not None
        else DEFAULT_LOOP_WINDOW
    )
    loop_threshold = (
        budget.max_loop_repetitions
        if budget is not None and budget.max_loop_repetitions is not None
        else DEFAULT_LOOP_THRESHOLD
    )
    retry_per_tool = (
        budget.max_retries_per_tool
        if budget is not None and budget.max_retries_per_tool is not None
        else DEFAULT_RETRY_PER_TOOL
    )
    retry_aggregate = (
        budget.max_retries_aggregate
        if budget is not None and budget.max_retries_aggregate is not None
        else DEFAULT_RETRY_AGGREGATE
    )
    cost_factor = (
        budget.max_cost_explosion_factor
        if budget is not None and budget.max_cost_explosion_factor is not None
        else DEFAULT_COST_FACTOR
    )

    findings: list[Finding] = []
    findings.extend(
        detect_loops(materialized, window=loop_window, threshold=loop_threshold)
    )
    findings.extend(
        detect_retry_storms(
            materialized,
            per_tool_threshold=retry_per_tool,
            aggregate_threshold=retry_aggregate,
        )
    )
    findings.extend(
        detect_cost_explosions(
            materialized,
            factor_threshold=cost_factor,
            min_baseline_usd=DEFAULT_COST_MIN_BASELINE_USD,
        )
    )

    findings.sort(
        key=lambda f: (_SEVERITY_ORDER[f.severity], f.detector, f.description)
    )
    return findings
