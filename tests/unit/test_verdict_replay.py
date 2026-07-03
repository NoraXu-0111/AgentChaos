"""Exit-code-5 precedence tests for compute_verdict with replay divergences."""
from __future__ import annotations

from datetime import UTC, datetime

from agentchaos.budget.schema import Budget
from agentchaos.chaos.policy import ChaosPolicy, ChaosTarget, ToolChaosPolicy
from agentchaos.profile.metrics import Metrics
from agentchaos.replay.schema import Divergence
from agentchaos.scenario.schema import Expectation
from agentchaos.trace.schema import AgentTurn, ChaosInjected
from agentchaos.verdict import (
    EXIT_BUDGET_OR_EXPECTATION_FAIL,
    EXIT_PASS,
    EXIT_REPLAY_DIVERGENCE,
    EXIT_TRANSPORT_FAIL,
    compute_verdict,
)


def _divergence() -> Divergence:
    return Divergence(
        kind="tool_call_mismatch",
        turn_index=0,
        detail="turn 0: tool call 0 differs",
        expected="get_order(sha256:aaa)",
        actual="lookup_customer(sha256:bbb)",
    )


def _chaos_policy() -> ChaosPolicy:
    return ChaosPolicy(
        expect_fallback=True,
        targets=[
            ChaosTarget(
                tool="get_order",
                policy=ToolChaosPolicy(failure_rate=1.0, status_code=503),
            )
        ],
    )


def _chaos_event() -> ChaosInjected:
    return ChaosInjected(
        run_id="r",
        seq=1,
        timestamp=datetime.now(UTC),
        target="get_order",
        policy="failure_rate=1.0 status_code=503",
        injection_type="status_code",
        value=503,
        tool_name="get_order",
    )


def _agent_error_turn() -> AgentTurn:
    return AgentTurn(
        run_id="r",
        seq=2,
        timestamp=datetime.now(UTC),
        turn_index=0,
        text="",
        latency_ms=5,
        error="agent blew up on tool error",
    )


def test_divergence_sets_exit_5() -> None:
    v = compute_verdict(
        Metrics(total_cost_usd=0.01),
        Expectation(),
        Budget(max_cost_usd=1.0),
        divergences=[_divergence()],
    )
    assert v.outcome == "fail"
    assert v.exit_code == EXIT_REPLAY_DIVERGENCE
    assert len(v.violations) == 1
    assert v.violations[0].kind == "replay"
    assert v.violations[0].name == "tool_call_mismatch"


def test_divergence_beats_budget_violation() -> None:
    v = compute_verdict(
        Metrics(total_cost_usd=0.10),
        Expectation(),
        Budget(max_cost_usd=0.05),
        divergences=[_divergence()],
    )
    assert v.exit_code == EXIT_REPLAY_DIVERGENCE
    kinds = {x.kind for x in v.violations}
    assert "replay" in kinds and "budget" in kinds


def test_session_error_beats_divergence() -> None:
    v = compute_verdict(
        Metrics(),
        Expectation(),
        Budget(),
        session_error="timeout",
        divergences=[_divergence()],
    )
    assert v.exit_code == EXIT_TRANSPORT_FAIL
    assert len(v.violations) == 1
    assert v.violations[0].name == "transport_error"


def test_divergence_beats_chaos_violation() -> None:
    v = compute_verdict(
        Metrics(),
        Expectation(),
        Budget(),
        chaos=_chaos_policy(),
        trace=[_chaos_event(), _agent_error_turn()],
        session_error=None,
        divergences=[_divergence()],
    )
    assert v.exit_code == EXIT_REPLAY_DIVERGENCE
    kinds = {x.kind for x in v.violations}
    assert "replay" in kinds and "chaos" in kinds


def test_no_divergences_kwarg_backwards_compatible() -> None:
    passing = compute_verdict(
        Metrics(total_cost_usd=0.01),
        Expectation(),
        Budget(max_cost_usd=1.0),
    )
    assert passing.outcome == "pass"
    assert passing.exit_code == EXIT_PASS

    failing = compute_verdict(
        Metrics(total_cost_usd=0.10),
        Expectation(),
        Budget(max_cost_usd=0.05),
    )
    assert failing.exit_code == EXIT_BUDGET_OR_EXPECTATION_FAIL
