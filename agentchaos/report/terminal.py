"""Terminal report — the v0 'wow moment'."""
from __future__ import annotations

from pathlib import Path

from agentchaos.detectors.schema import Finding, Severity
from agentchaos.profile.causes import PossibleCause
from agentchaos.profile.compare import Diff, MetricDelta
from agentchaos.profile.metrics import Metrics
from agentchaos.verdict import Verdict

_SEVERITY_ORDER: dict[Severity, int] = {"high": 0, "warn": 1, "info": 2}

# Map metric-delta name → (label, formatter)
_METRIC_DISPLAY: list[tuple[str, str, str]] = [
    ("total_cost_usd", "Cost", "$"),
    ("total_input_tokens", "Input tokens", "int"),
    ("total_output_tokens", "Output tokens", "int"),
    ("llm_calls", "LLM calls", "int"),
    ("tool_calls", "Tool calls", "int"),
    ("retries", "Retries", "int"),
    ("total_latency_ms", "Total latency", "ms"),
    ("max_turn_latency_ms", "Max turn latency", "ms"),
    ("errors", "Errors", "int"),
]

# Budget violation name → metric_delta name (for marking FAIL).
_BUDGET_TO_METRIC: dict[str, str] = {
    "max_cost_usd": "total_cost_usd",
    "max_total_latency_ms": "total_latency_ms",
    "max_turn_latency_ms": "max_turn_latency_ms",
    "max_tool_calls": "tool_calls",
    "max_llm_calls": "llm_calls",
    "max_retries": "retries",
    "max_input_tokens": "total_input_tokens",
    "max_cost_regression_pct": "total_cost_usd",
    "max_latency_regression_pct": "total_latency_ms",
    "max_tool_call_regression_pct": "tool_calls",
    "max_input_token_regression_pct": "total_input_tokens",
}

_WARN_PCT = 20.0


def _fmt(value: float | int | None, kind: str) -> str:
    if value is None:
        return "—"
    if kind == "$":
        return f"${value:.4f}"
    if kind == "ms":
        ms = float(value)
        return f"{ms / 1000:.2f}s" if ms >= 1000 else f"{int(ms)}ms"
    return f"{int(value)}"


def _fmt_delta(delta: MetricDelta) -> str:
    if delta.delta_abs is None:
        return "—"
    if delta.delta_pct is not None:
        sign = "+" if delta.delta_pct >= 0 else ""
        return f"{sign}{delta.delta_pct:.1f}%"
    if isinstance(delta.delta_abs, int):
        sign = "+" if delta.delta_abs >= 0 else ""
        return f"{sign}{int(delta.delta_abs)}"
    sign = "+" if delta.delta_abs >= 0 else ""
    return f"{sign}{delta.delta_abs:.4f}"


def _flag_for_metric(name: str, delta: MetricDelta | None, failed_metrics: set[str]) -> str:
    if name in failed_metrics:
        return "FAIL"
    if delta is not None and delta.delta_pct is not None and delta.delta_pct >= _WARN_PCT:
        return "WARN"
    return "PASS"


def _compact_sequence(names: list[str]) -> str:
    if not names:
        return "(none)"
    groups: list[str] = []
    prev: str | None = None
    count = 0
    for name in names:
        if name == prev:
            count += 1
            continue
        if prev is not None:
            groups.append(f"{prev} x{count}" if count > 1 else prev)
        prev = name
        count = 1
    if prev is not None:
        groups.append(f"{prev} x{count}" if count > 1 else prev)
    return " -> ".join(groups)


def render_terminal(
    *,
    scenario_name: str,
    verdict: Verdict,
    metrics: Metrics,
    diff: Diff | None,
    causes: list[PossibleCause],
    trace_path: Path | str,
    findings: list[Finding] | None = None,
) -> str:
    """Render the v0 verdict report as a multi-line string."""
    failed_metrics = {
        _BUDGET_TO_METRIC[v.name]
        for v in verdict.violations
        if v.name in _BUDGET_TO_METRIC
    }

    deltas_by_name: dict[str, MetricDelta] = {}
    if diff is not None:
        deltas_by_name = {d.name: d for d in diff.deltas}

    lines: list[str] = []
    lines.append(f"AgentChaos — {scenario_name}")
    lines.append("")
    lines.append(f"Verdict: {verdict.outcome.upper()}")
    lines.append("")

    # Why
    if verdict.violations:
        lines.append("Why:")
        for v in verdict.violations:
            lines.append(f"  - [{v.kind}] {v.name}: {v.detail}")
    else:
        lines.append("Why:")
        lines.append("  No expectation or budget violations.")
    lines.append("")

    # Scenario drift warning
    if diff is not None and diff.scenario_drift:
        lines.append("⚠ Scenario hash drift detected — baseline and candidate "
                     "use different scenario definitions.")
        lines.append("")

    # Metric table
    lines.append("Metrics:")
    header = f"  {'Metric':<22}{'Baseline':>14}{'Current':>14}{'Δ':>10}  {'Status':<6}"
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    for name, label, kind in _METRIC_DISPLAY:
        delta = deltas_by_name.get(name)
        baseline_val = delta.baseline if delta else None
        current_val = (
            delta.candidate if delta else getattr(metrics, name, None)
        )
        delta_str = _fmt_delta(delta) if delta else "—"
        flag = _flag_for_metric(name, delta, failed_metrics)
        lines.append(
            f"  {label:<22}"
            f"{_fmt(baseline_val, kind):>14}"
            f"{_fmt(current_val, kind):>14}"
            f"{delta_str:>10}  {flag:<6}"
        )
    lines.append("")

    # Tool sequence
    if diff is not None:
        lines.append("Tool sequence:")
        lines.append(f"  baseline: {_compact_sequence(diff.tool_sequence_baseline)}")
        lines.append(f"  current:  {_compact_sequence(diff.tool_sequence_candidate)}")
        lines.append("")
    else:
        seq = _compact_sequence([name for (name, _) in metrics.tool_sequence])
        lines.append("Tool sequence:")
        lines.append(f"  {seq}")
        lines.append("")

    # Detected patterns (findings)
    if findings:
        sorted_findings = sorted(
            findings,
            key=lambda f: (_SEVERITY_ORDER[f.severity], f.detector, f.description),
        )
        lines.append("Detected patterns:")
        for f in sorted_findings:
            lines.append(f"  - [{f.severity}]  {f.detector}: {f.description}")
        lines.append("")

    # Possible contributors
    if causes:
        lines.append("Possible contributors:")
        for c in causes:
            tag = ""
            if c.confidence == "computed" and c.contribution_usd is not None:
                tag = f"  [computed, ~${c.contribution_usd:.4f}]"
            elif c.confidence == "correlates":
                tag = "  [correlates]"
            lines.append(f"  - {c.description}{tag}")
        lines.append("")

    # Footer
    lines.append(f"Trace:    {trace_path}")
    lines.append(f"Fidelity: {metrics.fidelity}")
    lines.append(f"Exit code: {verdict.exit_code}")

    return "\n".join(lines)
