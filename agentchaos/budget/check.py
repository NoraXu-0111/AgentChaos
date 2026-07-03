"""Budget enforcement: absolute checks against metrics, regression checks against deltas."""
from __future__ import annotations

from agentchaos.budget.schema import Budget
from agentchaos.detectors.schema import Finding
from agentchaos.profile.metrics import Metrics
from agentchaos.violations import Violation

# Mapping from Budget field → (Metrics attr, human label, formatter)
_ABSOLUTE_CHECKS: list[tuple[str, str, str, str]] = [
    # (budget_field, metrics_attr, human_label, fmt)
    ("max_cost_usd", "total_cost_usd", "cost", "$"),
    ("max_total_latency_ms", "total_latency_ms", "total_latency_ms", "ms"),
    ("max_turn_latency_ms", "max_turn_latency_ms", "max_turn_latency_ms", "ms"),
    ("max_tool_calls", "tool_calls", "tool_calls", "count"),
    ("max_llm_calls", "llm_calls", "llm_calls", "count"),
    ("max_retries", "retries", "retries", "count"),
    ("max_input_tokens", "total_input_tokens", "input_tokens", "count"),
]

# Mapping from regression budget field → key in the deltas dict (delta_pct)
_REGRESSION_CHECKS: list[tuple[str, str, str]] = [
    ("max_cost_regression_pct", "total_cost_usd", "cost"),
    ("max_latency_regression_pct", "total_latency_ms", "latency"),
    ("max_tool_call_regression_pct", "tool_calls", "tool_calls"),
    ("max_input_token_regression_pct", "total_input_tokens", "input_tokens"),
]


def _format_value(value: float | int, unit: str) -> str:
    if unit == "$":
        return f"${value:.4f}"
    if unit == "ms":
        return f"{value} ms"
    return f"{value}"


def check_absolute(metrics: Metrics, budget: Budget) -> list[Violation]:
    """Return one Violation per absolute budget breach."""
    violations: list[Violation] = []
    for budget_field, metrics_attr, label, unit in _ABSOLUTE_CHECKS:
        limit = getattr(budget, budget_field)
        if limit is None:
            continue
        actual = getattr(metrics, metrics_attr)
        if actual is None:
            continue
        if actual > limit:
            violations.append(
                Violation(
                    kind="budget",
                    name=budget_field,
                    detail=(
                        f"{label} {_format_value(actual, unit)} exceeds limit "
                        f"{_format_value(limit, unit)}"
                    ),
                )
            )
    return violations


def check_detectors(findings: list[Finding], budget: Budget) -> list[Violation]:
    """Escalate findings to Violations only when the matching budget field is set.

    Mapping:
      - ``loop`` → ``max_loop_repetitions``
      - ``retry_storm`` (per-tool) → ``max_retries_per_tool``
      - ``retry_storm`` (aggregate) → ``max_retries_aggregate``
      - ``cost_explosion`` → ``max_cost_explosion_factor``
    """
    violations: list[Violation] = []
    for finding in findings:
        if finding.detector == "loop":
            if budget.max_loop_repetitions is None:
                continue
            violations.append(
                Violation(
                    kind="detector",
                    name="max_loop_repetitions",
                    detail=finding.description,
                )
            )
        elif finding.detector == "retry_storm":
            scope = finding.evidence.get("scope")
            if scope == "per_tool":
                if budget.max_retries_per_tool is None:
                    continue
                violations.append(
                    Violation(
                        kind="detector",
                        name="max_retries_per_tool",
                        detail=finding.description,
                    )
                )
            elif scope == "aggregate":
                if budget.max_retries_aggregate is None:
                    continue
                violations.append(
                    Violation(
                        kind="detector",
                        name="max_retries_aggregate",
                        detail=finding.description,
                    )
                )
        elif finding.detector == "cost_explosion":
            if budget.max_cost_explosion_factor is None:
                continue
            violations.append(
                Violation(
                    kind="detector",
                    name="max_cost_explosion_factor",
                    detail=finding.description,
                )
            )
    return violations


def check_regression(deltas: dict[str, float], budget: Budget) -> list[Violation]:
    """Return one Violation per regression-budget breach.

    ``deltas`` maps metric name to percent change vs baseline (e.g. 42.0 = +42%).
    Only positive deltas (regressions) trigger violations.
    """
    violations: list[Violation] = []
    for budget_field, delta_key, label in _REGRESSION_CHECKS:
        limit_pct = getattr(budget, budget_field)
        if limit_pct is None:
            continue
        actual_pct = deltas.get(delta_key)
        if actual_pct is None:
            continue
        if actual_pct > limit_pct:
            violations.append(
                Violation(
                    kind="regression_budget",
                    name=budget_field,
                    detail=(
                        f"{label} regressed +{actual_pct:.1f}% (limit +{limit_pct:.1f}%)"
                    ),
                )
            )
    return violations
