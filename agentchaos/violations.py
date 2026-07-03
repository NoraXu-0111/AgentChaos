"""Shared Violation type used by budget checks and the verdict module."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

ViolationKind = Literal["expectation", "budget", "regression_budget", "detector"]


class Violation(BaseModel):
    """One specific way a run failed an expectation or budget."""

    model_config = ConfigDict(extra="forbid")

    kind: ViolationKind
    name: str
    detail: str
