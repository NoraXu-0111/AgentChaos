"""Cost-explosion detector — flags outlier-cost model calls.

A call is an outlier when its cost is at least ``factor_threshold`` times the
leave-one-out median of the other model-call costs in the trace. The detector
also tries to attribute the spike to a probable driver:

- ``input_tokens`` if input token usage is also an outlier on the same call;
- ``repeated_tool_call`` if a ``ToolCall`` in the same ``turn_index`` shares an
  ``(name, args_hash)`` signature that repeats >=3 times overall;
- ``unknown`` otherwise.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from statistics import median
from typing import Any

from agentchaos.detectors.schema import Finding
from agentchaos.trace.schema import ModelCall, ToolCall, TraceEvent

_REPEAT_DRIVER_THRESHOLD = 3


def detect_cost_explosions(
    trace: Iterable[TraceEvent],
    *,
    factor_threshold: float = 5.0,
    min_baseline_usd: float = 0.0001,
) -> list[Finding]:
    """Return findings for every outlier model-call cost."""
    if factor_threshold <= 1.0:
        raise ValueError(f"factor_threshold must be > 1.0, got {factor_threshold}")
    if min_baseline_usd < 0:
        raise ValueError(f"min_baseline_usd must be >= 0, got {min_baseline_usd}")

    materialized = list(trace)
    model_calls: list[ModelCall] = [
        ev for ev in materialized if isinstance(ev, ModelCall) and ev.cost_usd is not None
    ]
    if len(model_calls) < 2:
        return []

    costs: list[float] = [mc.cost_usd for mc in model_calls]  # type: ignore[misc]
    input_tokens_series: list[int] = [
        mc.input_tokens for mc in model_calls if mc.input_tokens is not None
    ]

    # Repeated (name, args_hash) signatures across the whole trace — used by
    # the repeated-tool-call driver heuristic.
    tool_sig_counts: Counter[tuple[str, str]] = Counter()
    tools_by_turn: dict[int, list[ToolCall]] = {}
    for ev in materialized:
        if isinstance(ev, ToolCall):
            tool_sig_counts[(ev.name, ev.args_hash)] += 1
            tools_by_turn.setdefault(ev.turn_index, []).append(ev)

    findings: list[Finding] = []
    for idx, mc in enumerate(model_calls):
        others = costs[:idx] + costs[idx + 1 :]
        if not others:
            continue
        med = median(others)
        if med < min_baseline_usd:
            continue
        cost = mc.cost_usd
        assert cost is not None
        factor = cost / med
        if factor < factor_threshold:
            continue

        driver, driver_evidence = _identify_driver(
            mc,
            idx,
            input_tokens_series,
            factor_threshold,
            min_baseline_usd,
            tool_sig_counts,
            tools_by_turn,
        )

        findings.append(
            Finding(
                detector="cost_explosion",
                severity="high",
                description=(
                    f"model_call cost ${cost:.6f} is {factor:.1f}x the "
                    f"median ${med:.6f} (threshold {factor_threshold:.1f}x)"
                ),
                evidence={
                    "model": mc.model,
                    "name": mc.name,
                    "turn_index": mc.turn_index,
                    "cost_usd": cost,
                    "median_cost_usd": med,
                    "factor": factor,
                    "driver": driver,
                    "driver_evidence": driver_evidence,
                },
            )
        )

    return findings


def _identify_driver(
    mc: ModelCall,
    mc_index: int,
    input_tokens_series: list[int],
    factor_threshold: float,
    min_baseline_usd: float,
    tool_sig_counts: Counter[tuple[str, str]],
    tools_by_turn: dict[int, list[ToolCall]],
) -> tuple[str, dict[str, Any]]:
    # Driver 1 — input_tokens is also an outlier.
    if mc.input_tokens is not None and len(input_tokens_series) >= 2:
        # The mc.input_tokens value lives at some index in input_tokens_series;
        # build the leave-one-out median by removing the *first* match.
        others = list(input_tokens_series)
        try:
            others.remove(mc.input_tokens)
        except ValueError:
            others = input_tokens_series
        if others:
            tok_med = median(others)
            if tok_med >= 1 and mc.input_tokens / tok_med >= factor_threshold:
                return "input_tokens", {
                    "input_tokens": mc.input_tokens,
                    "median_input_tokens": tok_med,
                    "factor": mc.input_tokens / tok_med,
                }

    # Driver 2 — same-turn ToolCall whose signature repeats.
    same_turn_tools = tools_by_turn.get(mc.turn_index, [])
    for tc in same_turn_tools:
        count = tool_sig_counts[(tc.name, tc.args_hash)]
        if count >= _REPEAT_DRIVER_THRESHOLD:
            return "repeated_tool_call", {
                "tool": tc.name,
                "args_hash": tc.args_hash,
                "count": count,
            }

    # silence unused-arg warning for params kept for symmetry / future use.
    _ = (mc_index, min_baseline_usd)
    return "unknown", {}
