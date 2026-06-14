"""Tests for chaos injection decisions."""
from __future__ import annotations

import random

from agentchaos.chaos.injectors import decide_injection, policy_description
from agentchaos.chaos.policy import ToolChaosPolicy


def test_failure_rate_one_always_injects_status() -> None:
    rng = random.Random(0)
    for _ in range(20):
        d = decide_injection(ToolChaosPolicy(failure_rate=1.0, status_code=503), rng)
        assert d.inject is True
        assert d.injection_type == "status_code"
        assert d.status_code == 503
        assert d.latency_ms == 0


def test_failure_default_status_when_unset() -> None:
    rng = random.Random(0)
    d = decide_injection(ToolChaosPolicy(failure_rate=1.0), rng)
    assert d.injection_type == "status_code"
    assert d.status_code == 503


def test_seed_reproducible_over_twenty_calls() -> None:
    policy = ToolChaosPolicy(failure_rate=0.5, status_code=500)
    a = [decide_injection(policy, random.Random(42)).injection_type for _ in range(1)]
    # Build a full pattern under one seeded stream and compare to a second.
    rng1 = random.Random(42)
    rng2 = random.Random(42)
    pat1 = [decide_injection(policy, rng1).inject for _ in range(20)]
    pat2 = [decide_injection(policy, rng2).inject for _ in range(20)]
    assert pat1 == pat2
    # Sanity: a 0.5 rate over 20 draws should produce a mix.
    assert any(pat1) and not all(pat1)
    assert a  # touch the single-call path


def test_latency_only_when_failure_does_not_fire() -> None:
    # failure_rate 0 → roll never fires, latency applies.
    rng = random.Random(0)
    d = decide_injection(ToolChaosPolicy(latency_ms=250), rng)
    assert d.inject is True
    assert d.injection_type == "latency"
    assert d.latency_ms == 250
    assert d.status_code is None


def test_empty_policy_is_none() -> None:
    rng = random.Random(0)
    d = decide_injection(ToolChaosPolicy(), rng)
    assert d.inject is False
    assert d.injection_type == "none"


def test_failure_dominates_latency() -> None:
    # When the failure roll fires we must NOT also sleep.
    rng = random.Random(0)
    d = decide_injection(ToolChaosPolicy(failure_rate=1.0, status_code=502, latency_ms=999), rng)
    assert d.injection_type == "status_code"
    assert d.latency_ms == 0


def test_policy_description() -> None:
    assert "failure_rate=0.5" in policy_description(
        ToolChaosPolicy(failure_rate=0.5, status_code=503)
    )
    assert "latency_ms=200" in policy_description(ToolChaosPolicy(latency_ms=200))
    assert policy_description(ToolChaosPolicy()) == "no-op"
