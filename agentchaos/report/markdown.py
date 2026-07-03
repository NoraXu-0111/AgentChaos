"""Markdown report for PR comments — mirrors the terminal report."""
from __future__ import annotations

from pathlib import Path

from agentchaos import __version__
from agentchaos.detectors.schema import Finding
from agentchaos.profile.causes import PossibleCause
from agentchaos.profile.compare import Diff, MetricDelta
from agentchaos.profile.metrics import Metrics
from agentchaos.report.terminal import (
    _BUDGET_TO_METRIC,
    _METRIC_DISPLAY,
    _SEVERITY_ORDER,
    _compact_sequence,
    _flag_for_metric,
    _fmt,
    _fmt_delta,
)
from agentchaos.verdict import Verdict

MARKER_PREFIX = "<!-- agentchaos-report:"

_FLAG_TO_BADGE: dict[str, str] = {"FAIL": "❌ FAIL", "WARN": "⚠ WARN", "PASS": "✅"}


def comment_marker(scenario_name: str) -> str:
    """Return the hidden HTML marker line identifying this scenario's PR comment."""
    return f"{MARKER_PREFIX}{scenario_name} -->"


def _md_escape(text: str) -> str:
    """Escape '|', backticks, and newlines for safe use in table cells and bullets."""
    return (
        text.replace("|", "&#124;")
        .replace("`", "\\`")
        .replace("\r\n", " ")
        .replace("\n", " ")
        .replace("\r", " ")
    )


def render_markdown(
    *,
    scenario_name: str,
    verdict: Verdict,
    metrics: Metrics,
    diff: Diff | None,
    causes: list[PossibleCause],
    trace_path: Path | str,
    findings: list[Finding] | None = None,
) -> str:
    """Render the run report as GitHub-flavored markdown.

    The first line is :func:`comment_marker` for ``scenario_name`` so the
    GitHub Action can upsert one PR comment per scenario.
    """
    failed_metrics = {
        _BUDGET_TO_METRIC[v.name]
        for v in verdict.violations
        if v.name in _BUDGET_TO_METRIC
    }

    deltas_by_name: dict[str, MetricDelta] = {}
    if diff is not None:
        deltas_by_name = {d.name: d for d in diff.deltas}

    badge = "✅ PASS" if verdict.outcome == "pass" else "❌ FAIL"

    lines: list[str] = []
    lines.append(comment_marker(scenario_name))
    lines.append(f"## AgentChaos — {scenario_name}")
    lines.append("")
    lines.append(f"**Verdict: {badge}** (exit code {verdict.exit_code})")
    lines.append("")

    # Why
    lines.append("### Why")
    if verdict.violations:
        for v in verdict.violations:
            lines.append(f"- **[{v.kind}]** `{v.name}`: {_md_escape(v.detail)}")
    else:
        lines.append("No expectation or budget violations.")
    lines.append("")

    # Scenario drift warning
    if diff is not None and diff.scenario_drift:
        lines.append(
            "> ⚠ Scenario hash drift detected — baseline and candidate use "
            "different scenario definitions."
        )
        lines.append("")

    # Metric table
    lines.append("### Metrics")
    lines.append("| Metric | Baseline | Current | Δ | Status |")
    lines.append("| --- | ---: | ---: | ---: | :--- |")
    for name, label, kind in _METRIC_DISPLAY:
        delta = deltas_by_name.get(name)
        baseline_val = delta.baseline if delta else None
        current_val = delta.candidate if delta else getattr(metrics, name, None)
        delta_str = _fmt_delta(delta) if delta else "—"
        flag = _FLAG_TO_BADGE[_flag_for_metric(name, delta, failed_metrics)]
        lines.append(
            f"| {label} | {_fmt(baseline_val, kind)} | {_fmt(current_val, kind)} "
            f"| {delta_str} | {flag} |"
        )
    lines.append("")

    # Tool sequence
    lines.append("### Tool sequence")
    if diff is not None:
        lines.append(f"- baseline: `{_compact_sequence(diff.tool_sequence_baseline)}`")
        lines.append(f"- current: `{_compact_sequence(diff.tool_sequence_candidate)}`")
    else:
        seq = _compact_sequence([name for (name, _) in metrics.tool_sequence])
        lines.append(f"- `{seq}`")
    lines.append("")

    # Detected patterns (findings)
    if findings:
        sorted_findings = sorted(
            findings,
            key=lambda f: (_SEVERITY_ORDER[f.severity], f.detector, f.description),
        )
        lines.append("### Detected patterns")
        for f in sorted_findings:
            lines.append(f"- **[{f.severity}]** `{f.detector}`: {_md_escape(f.description)}")
        lines.append("")

    # Possible contributors
    if causes:
        lines.append("### Possible contributors")
        for c in causes:
            tag = ""
            if c.confidence == "computed" and c.contribution_usd is not None:
                tag = f"  _[computed, ~${c.contribution_usd:.4f}]_"
            elif c.confidence == "correlates":
                tag = "  _[correlates]_"
            lines.append(f"- {_md_escape(c.description)}{tag}")
        lines.append("")

    # Footer
    lines.append(
        f"<sub>Trace: `{trace_path}` · Fidelity: {metrics.fidelity} · "
        f"agentchaos {__version__}</sub>"
    )

    return "\n".join(lines)
