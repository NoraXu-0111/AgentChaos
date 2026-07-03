"""Tests for the terminal report formatter."""
from __future__ import annotations

from agentchaos.budget.schema import Budget
from agentchaos.detectors.schema import Finding
from agentchaos.profile.causes import PossibleCause
from agentchaos.profile.compare import diff
from agentchaos.profile.metrics import Metrics
from agentchaos.report.terminal import _compact_sequence, render_terminal
from agentchaos.scenario.schema import Expectation
from agentchaos.verdict import Verdict, compute_verdict


def test_compact_sequence_groups_consecutive() -> None:
    assert _compact_sequence(["a", "a", "a", "b", "c", "c"]) == "a x3 -> b -> c x2"


def test_compact_sequence_empty() -> None:
    assert _compact_sequence([]) == "(none)"


def test_compact_sequence_no_repeats() -> None:
    assert _compact_sequence(["a", "b", "c"]) == "a -> b -> c"


def test_render_pass_without_baseline() -> None:
    metrics = Metrics(total_cost_usd=0.01, tool_calls=2, by_tool={"get_order": 2})
    verdict = compute_verdict(
        metrics, Expectation(must_call_tools=["get_order"]), Budget(max_cost_usd=0.05)
    )
    out = render_terminal(
        scenario_name="t",
        verdict=verdict,
        metrics=metrics,
        diff=None,
        causes=[],
        trace_path="runs/x.jsonl",
    )
    assert "Verdict: PASS" in out
    assert "Exit code: 0" in out
    assert "Trace:" in out
    assert "Fidelity:" in out
    # Without baseline, deltas should all be em-dash.
    assert " — " in out


def test_render_fail_with_full_diff() -> None:
    b = Metrics(
        total_cost_usd=0.048,
        total_input_tokens=3420,
        total_output_tokens=812,
        total_latency_ms=4800,
        max_turn_latency_ms=4800,
        llm_calls=2,
        tool_calls=3,
        retries=1,
        by_tool={"get_order": 1, "create_return_label": 1},
        tool_sequence=[("get_order", "h1"), ("create_return_label", "h2")],
        by_model={"gpt-4o-mini": 0.048},
    )
    c = Metrics(
        total_cost_usd=0.068,
        total_input_tokens=5910,
        total_output_tokens=920,
        total_latency_ms=7200,
        max_turn_latency_ms=4900,
        llm_calls=4,
        tool_calls=9,
        retries=6,
        by_tool={"retrieve_policy": 1, "get_order": 6, "create_return_label": 1},
        tool_sequence=[
            ("retrieve_policy", "p"),
            ("get_order", "g"), ("get_order", "g"), ("get_order", "g"),
            ("get_order", "g"), ("get_order", "g"), ("get_order", "g"),
            ("create_return_label", "x"),
        ],
        by_model={"gpt-4o-mini": 0.068},
    )
    d = diff(b, c)
    verdict = compute_verdict(
        c,
        Expectation(),
        Budget(max_cost_usd=0.05, max_tool_calls=8, max_cost_regression_pct=20),
        diff=d,
    )
    causes = [
        PossibleCause(
            description="metadata.rag_chunks: 5 -> 12",
            correlates_with=["total_input_tokens"],
            confidence="correlates",
        ),
    ]
    out = render_terminal(
        scenario_name="refund-agent",
        verdict=verdict,
        metrics=c,
        diff=d,
        causes=causes,
        trace_path="runs/x.jsonl",
    )
    assert "Verdict: FAIL" in out
    assert "Exit code: 2" in out
    assert "+41.7%" in out  # cost delta
    assert "Cost" in out and "$0.0480" in out and "$0.0680" in out
    assert "retrieve_policy -> get_order x6" in out
    assert "metadata.rag_chunks" in out
    assert "FAIL" in out
    # Markers we expect for the violated metrics in the table.
    lines = out.split("\n")
    cost_line = next(line for line in lines if line.lstrip().startswith("Cost "))
    assert "FAIL" in cost_line


def test_render_scenario_drift_warning() -> None:
    b = Metrics()
    c = Metrics()
    d = diff(b, c, scenario_drift=True)
    verdict = Verdict(outcome="pass", violations=[], exit_code=0)
    out = render_terminal(
        scenario_name="t",
        verdict=verdict,
        metrics=c,
        diff=d,
        causes=[],
        trace_path="runs/x.jsonl",
    )
    assert "Scenario hash drift" in out


def test_render_findings_section_sorted_by_severity() -> None:
    findings = [
        Finding(
            detector="loop",
            severity="warn",
            description="warn-loop",
            evidence={},
        ),
        Finding(
            detector="cost_explosion",
            severity="high",
            description="high-cost",
            evidence={},
        ),
        Finding(
            detector="retry_storm",
            severity="warn",
            description="warn-retry",
            evidence={},
        ),
    ]
    verdict = Verdict(outcome="pass", violations=[], exit_code=0)
    out = render_terminal(
        scenario_name="t",
        verdict=verdict,
        metrics=Metrics(),
        diff=None,
        causes=[],
        trace_path="x",
        findings=findings,
    )
    assert "Detected patterns:" in out
    # Order: high first; then warns alphabetised by detector.
    high_idx = out.index("[high]")
    warn_cost_or_loop_idx = out.index("[warn]")
    assert high_idx < warn_cost_or_loop_idx
    # cost_explosion < loop < retry_storm alphabetically for the warn group.
    # high one is cost_explosion (only high). Then loop warn, then retry warn.
    loop_idx = out.index("loop: warn-loop")
    retry_idx = out.index("retry_storm: warn-retry")
    assert loop_idx < retry_idx


def test_render_findings_none_omits_section() -> None:
    out = render_terminal(
        scenario_name="t",
        verdict=Verdict(outcome="pass", violations=[], exit_code=0),
        metrics=Metrics(),
        diff=None,
        causes=[],
        trace_path="x",
        findings=None,
    )
    assert "Detected patterns" not in out


def test_render_findings_empty_omits_section() -> None:
    out = render_terminal(
        scenario_name="t",
        verdict=Verdict(outcome="pass", violations=[], exit_code=0),
        metrics=Metrics(),
        diff=None,
        causes=[],
        trace_path="x",
        findings=[],
    )
    assert "Detected patterns" not in out


def test_render_message_only_fidelity_shows_in_footer() -> None:
    metrics = Metrics(fidelity="message_only")
    verdict = Verdict(outcome="pass", violations=[], exit_code=0)
    out = render_terminal(
        scenario_name="t",
        verdict=verdict,
        metrics=metrics,
        diff=None,
        causes=[],
        trace_path="x",
    )
    assert "Fidelity: message_only" in out
