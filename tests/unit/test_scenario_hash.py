"""Tests for ``scenario_hash`` stability and sensitivity."""
from __future__ import annotations

from agentchaos.budget.schema import Budget
from agentchaos.scenario import Scenario, scenario_hash
from agentchaos.scenario.schema import AgentTarget, Expectation, UserTurn


def _make_scenario(**overrides) -> Scenario:
    defaults = {
        "id": "s1",
        "name": "scenario one",
        "description": "desc",
        "agent": AgentTarget(endpoint="http://localhost:8080/chat"),  # type: ignore[arg-type]
        "conversation": [UserTurn(user="hi"), UserTurn(user="bye")],
        "expect": Expectation(must_call_tools=["a", "b"]),
        "budgets": Budget(max_cost_usd=0.01),
        "metadata": {},
    }
    defaults.update(overrides)
    return Scenario(**defaults)  # type: ignore[arg-type]


def test_hash_stable_across_metadata_change() -> None:
    s1 = _make_scenario(metadata={"env": "dev", "branch": "main"})
    s2 = _make_scenario(metadata={"env": "prod", "branch": "feature-x"})
    assert scenario_hash(s1) == scenario_hash(s2)


def test_hash_changes_on_user_turn_change() -> None:
    s1 = _make_scenario()
    s2 = _make_scenario(conversation=[UserTurn(user="hi"), UserTurn(user="changed")])
    assert scenario_hash(s1) != scenario_hash(s2)


def test_hash_changes_on_endpoint_change() -> None:
    s1 = _make_scenario()
    s2 = _make_scenario(agent=AgentTarget(endpoint="http://localhost:9090/chat"))  # type: ignore[arg-type]
    assert scenario_hash(s1) != scenario_hash(s2)


def test_hash_changes_on_budget_change() -> None:
    s1 = _make_scenario()
    s2 = _make_scenario(budgets=Budget(max_cost_usd=0.99))
    assert scenario_hash(s1) != scenario_hash(s2)


def test_hash_changes_on_expectation_change() -> None:
    s1 = _make_scenario()
    s2 = _make_scenario(expect=Expectation(must_call_tools=["c"]))
    assert scenario_hash(s1) != scenario_hash(s2)


def test_hash_format() -> None:
    s = _make_scenario()
    h = scenario_hash(s)
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 64
    int(h.split(":")[1], 16)  # valid hex
