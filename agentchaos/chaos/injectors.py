"""Decide what fault (if any) to inject for one tool call.

The decision rule is deliberately simple and deterministic given a seeded RNG:

- Exactly ONE ``rng.random()`` draw per call, used against ``failure_rate``.
- If the failure roll fires, inject a ``status_code`` fault and DO NOT sleep.
- Only if the roll does NOT fire does ``latency_ms`` apply (deterministic, not
  rolled).
- An empty / no-op policy yields a ``none`` decision.
"""
from __future__ import annotations

import random
from typing import Literal

from pydantic import BaseModel, ConfigDict

from agentchaos.chaos.policy import ToolChaosPolicy

InjectionType = Literal["status_code", "latency", "none"]

# Default status code injected when failure_rate fires but no explicit code is set.
_DEFAULT_FAILURE_STATUS = 503


class ChaosDecision(BaseModel):
    """The outcome of evaluating a tool's chaos policy for one call."""

    model_config = ConfigDict(extra="forbid")

    inject: bool
    injection_type: InjectionType
    status_code: int | None = None
    latency_ms: int = 0
    policy_desc: str


def policy_description(policy: ToolChaosPolicy) -> str:
    """Human-readable one-line summary of a tool policy."""
    parts: list[str] = []
    if policy.failure_rate > 0:
        code = policy.status_code if policy.status_code is not None else _DEFAULT_FAILURE_STATUS
        parts.append(f"failure_rate={policy.failure_rate} status_code={code}")
    if policy.latency_ms > 0:
        parts.append(f"latency_ms={policy.latency_ms}")
    return "; ".join(parts) if parts else "no-op"


def decide_injection(policy: ToolChaosPolicy, rng: random.Random) -> ChaosDecision:
    """Evaluate ``policy`` against one RNG draw and return a decision.

    Always consumes exactly one ``rng.random()`` draw so the seeded sequence is
    reproducible regardless of which branch is taken.
    """
    desc = policy_description(policy)
    roll = rng.random()

    if policy.failure_rate > 0 and roll < policy.failure_rate:
        code = policy.status_code if policy.status_code is not None else _DEFAULT_FAILURE_STATUS
        return ChaosDecision(
            inject=True,
            injection_type="status_code",
            status_code=code,
            latency_ms=0,
            policy_desc=desc,
        )

    if policy.latency_ms > 0:
        return ChaosDecision(
            inject=True,
            injection_type="latency",
            status_code=None,
            latency_ms=policy.latency_ms,
            policy_desc=desc,
        )

    return ChaosDecision(
        inject=False,
        injection_type="none",
        status_code=None,
        latency_ms=0,
        policy_desc=desc,
    )
