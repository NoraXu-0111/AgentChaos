"""Replay divergence models.

Dependency-free except for pydantic — imported by ``verdict.py``, so it must
not import runner, transport, or scenario code (avoids import cycles; same
rule as ``chaos.policy``).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DivergenceKind = Literal[
    "turn_count_mismatch",
    "user_text_mismatch",
    "tool_call_mismatch",
    "extra_tool_call",
    "missing_tool_call",
    "model_call_count_mismatch",
    "agent_text_mismatch",
]


class Divergence(BaseModel):
    """One specific way candidate behavior departed from the recording."""

    model_config = ConfigDict(extra="forbid")

    kind: DivergenceKind
    turn_index: int = Field(..., ge=0)
    detail: str
    expected: str | None = None
    actual: str | None = None
