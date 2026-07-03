"""Tests for chaos policy models."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentchaos.chaos.policy import ChaosPolicy, ChaosTarget, ToolChaosPolicy


def _policy() -> ChaosPolicy:
    return ChaosPolicy(
        seed=42,
        targets=[
            ChaosTarget(tool="get_order", policy=ToolChaosPolicy(failure_rate=0.5, status_code=503)),
            ChaosTarget(tool="create_return_label", policy=ToolChaosPolicy(latency_ms=200)),
        ],
    )


def test_policy_for_matches() -> None:
    p = _policy()
    got = p.policy_for("get_order")
    assert got is not None
    assert got.failure_rate == 0.5
    assert got.status_code == 503


def test_policy_for_unknown_returns_none() -> None:
    assert _policy().policy_for("does_not_exist") is None


def test_empty_targets_is_valid() -> None:
    p = ChaosPolicy()
    assert p.targets == []
    assert p.policy_for("anything") is None
    assert p.expect_fallback is False


def test_failure_rate_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        ToolChaosPolicy(failure_rate=1.5)
    with pytest.raises(ValidationError):
        ToolChaosPolicy(failure_rate=-0.1)


def test_status_code_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        ToolChaosPolicy(status_code=399)
    with pytest.raises(ValidationError):
        ToolChaosPolicy(status_code=600)


def test_negative_latency_rejected() -> None:
    with pytest.raises(ValidationError):
        ToolChaosPolicy(latency_ms=-1)


def test_extra_field_forbidden() -> None:
    with pytest.raises(ValidationError):
        ToolChaosPolicy(failure_rate=0.1, malformed_response_rate=0.5)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        ChaosPolicy(seed=1, unexpected=True)  # type: ignore[call-arg]
