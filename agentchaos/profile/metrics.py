"""Metrics produced by aggregating a trace.

Phase 4 ships ``aggregate(trace) -> Metrics`` plus structured breakdowns
(``by_model``, ``by_tool``, ``tool_sequence``).
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agentchaos.trace.schema import (
    AgentTurn,
    ModelCall,
    Retry,
    ToolCall,
    TraceEvent,
)

FidelityLiteral = Literal["full", "aggregate", "message_only"]

_FIDELITY_RANK: dict[str, int] = {
    "full": 0,
    "aggregate": 1,
    "message_only": 2,
}


class Metrics(BaseModel):
    """Aggregate metrics for a single run."""

    model_config = ConfigDict(extra="forbid")

    total_cost_usd: float | None = None
    total_input_tokens: int | None = None
    total_output_tokens: int | None = None
    total_latency_ms: int = 0
    max_turn_latency_ms: int = 0
    llm_calls: int = 0
    tool_calls: int = 0
    retries: int = 0
    errors: int = 0
    fidelity: FidelityLiteral = "full"

    by_model: dict[str, float] = Field(default_factory=dict)
    by_tool: dict[str, int] = Field(default_factory=dict)
    tool_sequence: list[tuple[str, str]] = Field(default_factory=list)


def aggregate(trace: Iterable[TraceEvent]) -> Metrics:
    """Walk a trace and produce a :class:`Metrics`."""
    total_cost = 0.0
    cost_seen = False
    total_input = 0
    input_seen = False
    total_output = 0
    output_seen = False
    total_latency = 0
    max_turn_latency = 0
    llm_calls = 0
    tool_calls = 0
    retries = 0
    errors = 0
    by_model: dict[str, float] = defaultdict(float)
    by_tool: dict[str, int] = defaultdict(int)
    tool_sequence: list[tuple[str, str]] = []

    fidelity_str: str = "full"
    fidelity_seen = False

    for ev in trace:
        if isinstance(ev, ModelCall):
            llm_calls += 1
            if ev.cost_usd is not None:
                total_cost += ev.cost_usd
                cost_seen = True
                by_model[ev.model] += ev.cost_usd
            if ev.input_tokens is not None:
                total_input += ev.input_tokens
                input_seen = True
            if ev.output_tokens is not None:
                total_output += ev.output_tokens
                output_seen = True
        elif isinstance(ev, ToolCall):
            tool_calls += 1
            retries += ev.retries
            by_tool[ev.name] += 1
            tool_sequence.append((ev.name, ev.args_hash))
        elif isinstance(ev, Retry):
            retries += 1
        elif isinstance(ev, AgentTurn):
            total_latency += ev.latency_ms
            max_turn_latency = max(max_turn_latency, ev.latency_ms)
            if ev.error is not None:
                errors += 1
            fidelity_seen = True
            if _FIDELITY_RANK[ev.fidelity] > _FIDELITY_RANK[fidelity_str]:
                fidelity_str = ev.fidelity
            # Aggregate-tier responses bring cost via top-level usage.
            if ev.fidelity != "full" and ev.usage is not None:
                u_cost = ev.usage.get("cost_usd")
                if u_cost is not None:
                    try:
                        total_cost += float(u_cost)
                        cost_seen = True
                    except (TypeError, ValueError):
                        pass
                u_in = ev.usage.get("input_tokens")
                if u_in is not None:
                    try:
                        total_input += int(u_in)
                        input_seen = True
                    except (TypeError, ValueError):
                        pass
                u_out = ev.usage.get("output_tokens")
                if u_out is not None:
                    try:
                        total_output += int(u_out)
                        output_seen = True
                    except (TypeError, ValueError):
                        pass

    final_fidelity: FidelityLiteral = (
        "message_only" if not fidelity_seen else fidelity_str  # type: ignore[assignment]
    )

    return Metrics(
        total_cost_usd=round(total_cost, 6) if cost_seen else None,
        total_input_tokens=total_input if input_seen else None,
        total_output_tokens=total_output if output_seen else None,
        total_latency_ms=total_latency,
        max_turn_latency_ms=max_turn_latency,
        llm_calls=llm_calls,
        tool_calls=tool_calls,
        retries=retries,
        errors=errors,
        fidelity=final_fidelity,
        by_model=dict(by_model),
        by_tool=dict(by_tool),
        tool_sequence=tool_sequence,
    )
