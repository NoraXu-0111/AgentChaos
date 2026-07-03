"""Pydantic models for detector findings.

A :class:`Finding` is a neutral observation produced by a detector. The
verdict layer is responsible for deciding whether a finding escalates to a
:class:`~agentchaos.violations.Violation`; findings themselves are not
pass/fail signals.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["info", "warn", "high"]
DetectorName = Literal["loop", "retry_storm", "cost_explosion"]


class Finding(BaseModel):
    """One observation emitted by a detector."""

    model_config = ConfigDict(extra="forbid")

    detector: DetectorName
    severity: Severity
    description: str
    evidence: dict[str, Any] = Field(default_factory=dict)
