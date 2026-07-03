"""Tests for the markdown (PR comment) report renderer."""
from __future__ import annotations

from agentchaos.budget.schema import Budget
from agentchaos.detectors.schema import Finding
from agentchaos.profile.causes import PossibleCause
from agentchaos.profile.compare import diff
from agentchaos.profile.metrics import Metrics
from agentchaos.report.markdown import comment_marker, render_markdown
from agentchaos.report.terminal import _METRIC_DISPLAY
from agentchaos.scenario.schema import Expectation
from agentchaos.verdict import Verdict, compute_verdict
from agentchaos.violations import Violation


def _baseline_metrics() -> Metrics:
    return Metrics(
        total_cost_usd=0.0010,
        total_input_tokens=1850,
        total_output_tokens=150,
        total_latency_ms=1200,
        max_turn_latency_ms=1200,
        llm_calls=2,
        tool_calls=2,
        retries=0,
        by_tool={"get_order": 1, "create_return_label": 1},
        tool_sequence=[("get_order", "h1"), ("create_return_label", "h2")],
        by_model={"gpt-4o-mini": 0.0010},
    )


def _candidate_metrics() -> Metrics:
    return Metrics(
        total_cost_usd=0.0034,
        total_input_tokens=3530,
        total_output_tokens=180,
        total_latency_ms=2400,
        max_turn_latency_ms=2400,
        llm_calls=3,
        tool_calls=4,
        retries=1,
        by_tool={"get_order": 3, "create_return_label": 1},
        tool_sequence=[
            ("get_order", "g"), ("get_order", "g"), ("get_order", "g"),
            ("create_return_label", "x"),
        ],
        by_model={"gpt-4o-mini": 0.0034},
    )


def _metric_rows(out: str) -> list[str]:
    labels = {label for (_, label, _) in _METRIC_DISPLAY}
    return [
        line for line in out.split("\n")
        if line.startswith("| ") and line.split("|")[1].strip() in labels
    ]


def test_marker_is_first_line() -> None:
    out = render_markdown(
        scenario_name="refund-demo",
        verdict=Verdict(outcome="pass", violations=[], exit_code=0),
        metrics=Metrics(),
        diff=None,
        causes=[],
        trace_path="runs/x.jsonl",
    )
    first = out.split("\n")[0]
    assert first == comment_marker("refund-demo")
    assert first == "<!-- agentchaos-report:refund-demo -->"


def test_fail_run_full_sections() -> None:
    b, c = _baseline_metrics(), _candidate_metrics()
    d = diff(b, c)
    verdict = compute_verdict(
        c,
        Expectation(),
        Budget(max_cost_usd=0.002, max_cost_regression_pct=20),
        diff=d,
    )
    findings = [
        Finding(detector="loop", severity="high", description="get_order repeated 3x", evidence={}),
    ]
    causes = [
        PossibleCause(
            description="metadata.rag_chunks: 5 -> 12",
            correlates_with=["total_input_tokens"],
            confidence="correlates",
        ),
        PossibleCause(
            description="model swap gpt-4o-mini -> gpt-4o",
            correlates_with=["total_cost_usd"],
            confidence="computed",
            contribution_usd=0.0024,
        ),
    ]
    out = render_markdown(
        scenario_name="refund-demo",
        verdict=verdict,
        metrics=c,
        diff=d,
        causes=causes,
        trace_path="runs/x.jsonl",
        findings=findings,
    )
    assert "**Verdict: ❌ FAIL** (exit code 2)" in out
    assert "### Why" in out
    cost_row = next(r for r in _metric_rows(out) if "| Cost |" in r)
    assert "$0.0010" in cost_row
    assert "$0.0034" in cost_row
    assert "+240.0%" in cost_row
    assert "❌ FAIL" in cost_row
    assert "### Detected patterns" in out
    assert "- **[high]** `loop`: get_order repeated 3x" in out
    assert "### Possible contributors" in out
    assert "_[correlates]_" in out
    assert "_[computed, ~$0.0024]_" in out
    assert "Fidelity: full" in out


def test_pass_run_no_baseline() -> None:
    metrics = Metrics(
        total_cost_usd=0.001,
        tool_calls=2,
        by_tool={"get_order": 2},
        tool_sequence=[("get_order", "a"), ("get_order", "a")],
    )
    verdict = compute_verdict(
        metrics, Expectation(must_call_tools=["get_order"]), Budget(max_cost_usd=0.05)
    )
    out = render_markdown(
        scenario_name="t",
        verdict=verdict,
        metrics=metrics,
        diff=None,
        causes=[],
        trace_path="runs/x.jsonl",
    )
    assert "**Verdict: ✅ PASS** (exit code 0)" in out
    assert "No expectation or budget violations." in out
    assert "drift" not in out
    for row in _metric_rows(out):
        assert row.split("|")[2].strip() == "—"  # baseline column
    assert "- `get_order x2`" in out
    assert "- baseline:" not in out


def test_scenario_drift_blockquote() -> None:
    d = diff(Metrics(), Metrics(), scenario_drift=True)
    out = render_markdown(
        scenario_name="t",
        verdict=Verdict(outcome="pass", violations=[], exit_code=0),
        metrics=Metrics(),
        diff=d,
        causes=[],
        trace_path="x",
    )
    assert "> ⚠ Scenario hash drift detected" in out


def test_pipe_and_html_escaped_in_details() -> None:
    verdict = Verdict(
        outcome="fail",
        violations=[
            Violation(
                kind="budget",
                name="max_cost_usd",
                detail="cost | spiked `here` <script>alert(1)</script>",
            ),
        ],
        exit_code=2,
    )
    out = render_markdown(
        scenario_name="t",
        verdict=verdict,
        metrics=Metrics(),
        diff=None,
        causes=[],
        trace_path="x",
    )
    why_line = next(line for line in out.split("\n") if "max_cost_usd" in line)
    assert "&#124;" in why_line
    assert "cost |" not in why_line
    assert "\\`here\\`" in why_line
    for row in _metric_rows(out):
        assert row.count("|") == 6
    assert len(_metric_rows(out)) == 9


def test_metric_rows_match_terminal_order() -> None:
    out = render_markdown(
        scenario_name="t",
        verdict=Verdict(outcome="pass", violations=[], exit_code=0),
        metrics=Metrics(),
        diff=None,
        causes=[],
        trace_path="x",
    )
    labels = [row.split("|")[1].strip() for row in _metric_rows(out)]
    assert labels == [label for (_, label, _) in _METRIC_DISPLAY]
    assert len(labels) == 9
