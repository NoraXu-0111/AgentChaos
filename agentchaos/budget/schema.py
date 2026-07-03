"""Budget definition for absolute and regression constraints."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Budget(BaseModel):
    """Operational constraints for a scenario run.

    Absolute budgets are enforced on every run.
    Regression budgets (``*_regression_pct``) are only enforced when a
    baseline diff is provided.
    """

    model_config = ConfigDict(extra="forbid")

    # absolute
    max_cost_usd: float | None = Field(default=None, ge=0)
    max_total_latency_ms: int | None = Field(default=None, ge=0)
    max_turn_latency_ms: int | None = Field(default=None, ge=0)
    max_tool_calls: int | None = Field(default=None, ge=0)
    max_llm_calls: int | None = Field(default=None, ge=0)
    max_retries: int | None = Field(default=None, ge=0)
    max_input_tokens: int | None = Field(default=None, ge=0)

    # regression (vs baseline; only enforced when a Diff is provided)
    max_cost_regression_pct: float | None = Field(default=None, ge=0)
    max_latency_regression_pct: float | None = Field(default=None, ge=0)
    max_tool_call_regression_pct: float | None = Field(default=None, ge=0)
    max_input_token_regression_pct: float | None = Field(default=None, ge=0)

    # detector thresholds — when set, the matching detector finding escalates
    # to a Violation (kind="detector"). Detectors themselves always run.
    max_loop_repetitions: int | None = Field(default=None, ge=2)
    loop_window: int | None = Field(default=None, ge=2)
    max_retries_per_tool: int | None = Field(default=None, ge=1)
    max_retries_aggregate: int | None = Field(default=None, ge=1)
    max_cost_explosion_factor: float | None = Field(default=None, gt=1.0)
