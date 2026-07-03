"""Retry-storm detector — flags per-tool and aggregate retry spikes."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from agentchaos.detectors.schema import Finding, Severity
from agentchaos.trace.schema import Retry, ToolCall, TraceEvent


def detect_retry_storms(
    trace: Iterable[TraceEvent],
    *,
    per_tool_threshold: int = 3,
    aggregate_threshold: int = 6,
) -> list[Finding]:
    """Detect spikes in retry counts.

    Per-tool retries come from ``ToolCall.retries``. Standalone ``Retry`` events
    count toward the aggregate only (they have no tool name attached). A
    finding is emitted per tool whose retries hit ``per_tool_threshold`` and
    one aggregate finding when the grand total hits ``aggregate_threshold``.

    Severity is ``"high"`` once the count reaches twice the threshold, else
    ``"warn"``.
    """
    if per_tool_threshold < 1:
        raise ValueError(f"per_tool_threshold must be >= 1, got {per_tool_threshold}")
    if aggregate_threshold < 1:
        raise ValueError(f"aggregate_threshold must be >= 1, got {aggregate_threshold}")

    per_tool: dict[str, int] = defaultdict(int)
    retry_event_count = 0

    for ev in trace:
        if isinstance(ev, ToolCall):
            if ev.retries > 0:
                per_tool[ev.name] += ev.retries
        elif isinstance(ev, Retry):
            retry_event_count += 1

    findings: list[Finding] = []

    # Per-tool findings — sorted by tool name for determinism.
    for tool in sorted(per_tool):
        retries = per_tool[tool]
        if retries < per_tool_threshold:
            continue
        severity: Severity = "high" if retries >= 2 * per_tool_threshold else "warn"
        findings.append(
            Finding(
                detector="retry_storm",
                severity=severity,
                description=(
                    f"{tool} accumulated {retries} retries "
                    f"(threshold {per_tool_threshold})"
                ),
                evidence={
                    "scope": "per_tool",
                    "tool": tool,
                    "retries": retries,
                    "threshold": per_tool_threshold,
                },
            )
        )

    # Aggregate finding.
    aggregate_retries = sum(per_tool.values()) + retry_event_count
    if aggregate_retries >= aggregate_threshold:
        aggregate_severity: Severity = (
            "high" if aggregate_retries >= 2 * aggregate_threshold else "warn"
        )
        findings.append(
            Finding(
                detector="retry_storm",
                severity=aggregate_severity,
                description=(
                    f"aggregate retries reached {aggregate_retries} "
                    f"(threshold {aggregate_threshold})"
                ),
                evidence={
                    "scope": "aggregate",
                    "retries": aggregate_retries,
                    "threshold": aggregate_threshold,
                },
            )
        )

    return findings
