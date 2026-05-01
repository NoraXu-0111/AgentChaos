"""Metrics produced by aggregating a trace.

Phase 1 defines just the fields needed for budget checks.
Phase 4 will add ``aggregate(trace)`` plus ``by_model`` / ``by_tool`` /
``tool_sequence`` breakdowns.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FidelityTier = Literal["full", "aggregate", "message_only"]


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
    fidelity: FidelityTier = "full"

    # Phase 4 will populate these.
    by_model: dict[str, float] = Field(default_factory=dict)
    by_tool: dict[str, int] = Field(default_factory=dict)
    tool_sequence: list[tuple[str, str]] = Field(default_factory=list)
