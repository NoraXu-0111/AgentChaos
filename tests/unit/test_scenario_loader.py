"""Tests for the YAML scenario loader."""
from __future__ import annotations

from pathlib import Path

import pytest

from agentchaos.scenario import LoaderError, load_scenario

FIXTURES = Path(__file__).parent.parent / "fixtures" / "scenarios"


def test_load_valid_minimal() -> None:
    s = load_scenario(FIXTURES / "valid_minimal.yaml")
    assert s.id == "minimal"
    assert s.name == "minimal scenario"
    assert len(s.conversation) == 1
    assert s.conversation[0].user == "hello"
    assert str(s.agent.endpoint).startswith("http://localhost:8080")


def test_load_valid_full() -> None:
    s = load_scenario(FIXTURES / "valid_full.yaml")
    assert s.id == "refund-agent"
    assert s.budgets.max_cost_usd == 0.05
    assert s.expect.must_call_tools == ["get_order"]
    assert s.metadata == {"env": "dev"}


def test_load_valid_only_expect() -> None:
    s = load_scenario(FIXTURES / "valid_only_expect.yaml")
    assert s.expect.final_response_contains == ["hi"]
    assert s.budgets.max_cost_usd is None


def test_load_valid_only_budget() -> None:
    s = load_scenario(FIXTURES / "valid_only_budget.yaml")
    assert s.budgets.max_cost_usd == 0.01
    assert s.expect.must_call_tools == []


def test_env_interpolation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_TOKEN", "secret-xyz")
    s = load_scenario(FIXTURES / "valid_with_env.yaml")
    assert s.agent.headers["Authorization"] == "Bearer secret-xyz"


def test_env_interpolation_missing_var_kept_literal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_TOKEN", raising=False)
    s = load_scenario(FIXTURES / "valid_with_env.yaml")
    assert "${TEST_TOKEN}" in s.agent.headers["Authorization"]


def test_invalid_missing_agent() -> None:
    with pytest.raises(LoaderError) as exc:
        load_scenario(FIXTURES / "invalid_missing_agent.yaml")
    assert "agent" in str(exc.value).lower()


def test_invalid_empty_conversation() -> None:
    with pytest.raises(LoaderError) as exc:
        load_scenario(FIXTURES / "invalid_empty_conversation.yaml")
    assert "conversation" in str(exc.value).lower()


def test_invalid_bad_endpoint() -> None:
    with pytest.raises(LoaderError) as exc:
        load_scenario(FIXTURES / "invalid_bad_endpoint.yaml")
    msg = str(exc.value).lower()
    assert "endpoint" in msg or "url" in msg


def test_invalid_extra_field() -> None:
    with pytest.raises(LoaderError) as exc:
        load_scenario(FIXTURES / "invalid_extra_field.yaml")
    assert "nonsense_extra_field" in str(exc.value) or "extra" in str(exc.value).lower()


def test_invalid_id_with_space() -> None:
    with pytest.raises(LoaderError) as exc:
        load_scenario(FIXTURES / "invalid_id_with_space.yaml")
    assert "whitespace" in str(exc.value).lower()


def test_missing_file() -> None:
    with pytest.raises(LoaderError) as exc:
        load_scenario(FIXTURES / "nonexistent.yaml")
    assert "not found" in str(exc.value).lower()


def test_empty_file(tmp_path: Path) -> None:
    f = tmp_path / "empty.yaml"
    f.write_text("")
    with pytest.raises(LoaderError) as exc:
        load_scenario(f)
    assert "empty" in str(exc.value).lower()


def test_malformed_yaml(tmp_path: Path) -> None:
    f = tmp_path / "bad.yaml"
    f.write_text("id: ok\nagent:\n  - this is\n   not: valid")
    with pytest.raises(LoaderError) as exc:
        load_scenario(f)
    assert "yaml" in str(exc.value).lower() or "invalid" in str(exc.value).lower()


def test_top_level_not_mapping(tmp_path: Path) -> None:
    f = tmp_path / "list.yaml"
    f.write_text("- just a list\n")
    with pytest.raises(LoaderError) as exc:
        load_scenario(f)
    assert "mapping" in str(exc.value).lower()
