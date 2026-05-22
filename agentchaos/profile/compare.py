"""Compare two :class:`Metrics` and produce a :class:`Diff`."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agentchaos.profile.metrics import Metrics

# Mapping from delta name to attribute on Metrics.
_TRACKED: list[tuple[str, str]] = [
    ("total_cost_usd", "total_cost_usd"),
    ("total_input_tokens", "total_input_tokens"),
    ("total_output_tokens", "total_output_tokens"),
    ("total_latency_ms", "total_latency_ms"),
    ("max_turn_latency_ms", "max_turn_latency_ms"),
    ("llm_calls", "llm_calls"),
    ("tool_calls", "tool_calls"),
    ("retries", "retries"),
    ("errors", "errors"),
]


class MetricDelta(BaseModel):
    """One metric's baseline → candidate change."""

    model_config = ConfigDict(extra="forbid")

    name: str
    baseline: float | int | None
    candidate: float | int | None
    delta_abs: float | int | None
    delta_pct: float | None


class Diff(BaseModel):
    """Structured diff between two runs."""

    model_config = ConfigDict(extra="forbid")

    deltas: list[MetricDelta]
    tool_sequence_baseline: list[str] = Field(default_factory=list)
    tool_sequence_candidate: list[str] = Field(default_factory=list)
    scenario_drift: bool = False
    by_model_baseline: dict[str, float] = Field(default_factory=dict)
    by_model_candidate: dict[str, float] = Field(default_factory=dict)
    by_tool_baseline: dict[str, int] = Field(default_factory=dict)
    by_tool_candidate: dict[str, int] = Field(default_factory=dict)

    def delta_pct_map(self) -> dict[str, float]:
        """Return a name → delta_pct mapping for ``check_regression``."""
        out: dict[str, float] = {}
        for d in self.deltas:
            if d.delta_pct is not None:
                out[d.name] = d.delta_pct
        return out


def _delta(b: float | int | None, c: float | int | None) -> tuple[
    float | int | None, float | None
]:
    if b is None or c is None:
        return None, None
    abs_delta = c - b
    if b == 0:
        # Percentage is undefined when the baseline is zero. Surface the
        # absolute delta but leave delta_pct=None so callers don't get inf.
        return abs_delta, None
    return abs_delta, ((c - b) / b) * 100.0


def diff(baseline: Metrics, candidate: Metrics, *, scenario_drift: bool = False) -> Diff:
    """Produce a structured :class:`Diff` between two metric snapshots."""
    deltas: list[MetricDelta] = []
    for delta_name, attr in _TRACKED:
        b_val = getattr(baseline, attr)
        c_val = getattr(candidate, attr)
        abs_d, pct_d = _delta(b_val, c_val)
        deltas.append(
            MetricDelta(
                name=delta_name,
                baseline=b_val,
                candidate=c_val,
                delta_abs=abs_d,
                delta_pct=pct_d,
            )
        )

    return Diff(
        deltas=deltas,
        tool_sequence_baseline=[name for (name, _) in baseline.tool_sequence],
        tool_sequence_candidate=[name for (name, _) in candidate.tool_sequence],
        scenario_drift=scenario_drift,
        by_model_baseline=dict(baseline.by_model),
        by_model_candidate=dict(candidate.by_model),
        by_tool_baseline=dict(baseline.by_tool),
        by_tool_candidate=dict(candidate.by_tool),
    )
