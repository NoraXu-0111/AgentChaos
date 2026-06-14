"""Chaos policy models.

Dependency-free except for pydantic — this module is imported by
``scenario.schema`` so it must not import back into scenario or runner code
(avoids an import cycle).
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ToolChaosPolicy(BaseModel):
    """Fault-injection knobs for a single tool."""

    model_config = ConfigDict(extra="forbid")

    failure_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    latency_ms: int = Field(default=0, ge=0)
    status_code: int | None = Field(default=None, ge=400, le=599)


class ChaosTarget(BaseModel):
    """A tool name paired with the policy applied to it."""

    model_config = ConfigDict(extra="forbid")

    tool: str = Field(..., min_length=1)
    policy: ToolChaosPolicy


class ChaosPolicy(BaseModel):
    """Whole-scenario chaos configuration."""

    model_config = ConfigDict(extra="forbid")

    seed: int | None = None
    targets: list[ChaosTarget] = Field(default_factory=list)
    expect_fallback: bool = False

    def policy_for(self, tool_name: str) -> ToolChaosPolicy | None:
        """Return the policy for ``tool_name``, or ``None`` if untargeted."""
        for target in self.targets:
            if target.tool == tool_name:
                return target.policy
        return None
