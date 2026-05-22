"""Tests for diff()."""
from __future__ import annotations

from agentchaos.profile.compare import diff
from agentchaos.profile.metrics import Metrics


def test_diff_each_metric_simple_growth() -> None:
    b = Metrics(
        total_cost_usd=0.001, total_input_tokens=100, total_output_tokens=20,
        total_latency_ms=300, max_turn_latency_ms=300,
        llm_calls=1, tool_calls=1, retries=0, errors=0,
    )
    c = Metrics(
        total_cost_usd=0.002, total_input_tokens=200, total_output_tokens=40,
        total_latency_ms=600, max_turn_latency_ms=400,
        llm_calls=2, tool_calls=3, retries=1, errors=0,
    )
    d = diff(b, c)
    by_name = {x.name: x for x in d.deltas}
    assert by_name["total_cost_usd"].delta_pct == 100.0
    assert by_name["total_input_tokens"].delta_pct == 100.0
    assert by_name["tool_calls"].delta_abs == 2
    assert by_name["retries"].delta_pct is None  # baseline=0


def test_diff_handles_none_values() -> None:
    b = Metrics(total_cost_usd=None)
    c = Metrics(total_cost_usd=0.005)
    d = diff(b, c)
    by_name = {x.name: x for x in d.deltas}
    assert by_name["total_cost_usd"].delta_abs is None
    assert by_name["total_cost_usd"].delta_pct is None


def test_diff_scenario_drift_flag() -> None:
    d = diff(Metrics(), Metrics(), scenario_drift=True)
    assert d.scenario_drift is True


def test_diff_carries_breakdown_dicts() -> None:
    b = Metrics(by_model={"gpt-4o-mini": 0.001}, by_tool={"get_order": 1})
    c = Metrics(by_model={"gpt-4o": 0.005}, by_tool={"get_order": 3})
    d = diff(b, c)
    assert d.by_model_baseline == {"gpt-4o-mini": 0.001}
    assert d.by_model_candidate == {"gpt-4o": 0.005}
    assert d.by_tool_baseline == {"get_order": 1}
    assert d.by_tool_candidate == {"get_order": 3}


def test_diff_carries_tool_sequence_names() -> None:
    b = Metrics(tool_sequence=[("get_order", "h1"), ("create_label", "h2")])
    c = Metrics(tool_sequence=[("retrieve_policy", "h0"), ("get_order", "h1")])
    d = diff(b, c)
    assert d.tool_sequence_baseline == ["get_order", "create_label"]
    assert d.tool_sequence_candidate == ["retrieve_policy", "get_order"]


def test_delta_pct_map_excludes_none() -> None:
    b = Metrics(total_cost_usd=0.001, retries=0)
    c = Metrics(total_cost_usd=0.002, retries=2)
    d = diff(b, c)
    m = d.delta_pct_map()
    assert m["total_cost_usd"] == 100.0
    assert "retries" not in m  # baseline 0 → pct undefined
