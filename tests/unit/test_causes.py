"""Tests for cause detection rules."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agentchaos.profile.causes import find_causes
from agentchaos.profile.compare import diff
from agentchaos.profile.metrics import aggregate
from agentchaos.runner.session import args_hash
from agentchaos.trace.schema import (
    AgentTurn,
    ModelCall,
    ToolCall,
    UserTurn,
)


def _ts(s: int) -> datetime:
    return datetime(2026, 4, 30, 12, 0, s, tzinfo=UTC)


def _tc(turn: int, idx: int, name: str, args: dict, *, retries: int = 0) -> ToolCall:
    return ToolCall(
        run_id="r", seq=idx, timestamp=_ts(idx), session_id="s",
        turn_index=turn, call_index=idx, name=name,
        args=args, args_hash=args_hash(args),
        latency_ms=50, result_summary="ok", retries=retries,
    )


def _mc(
    turn: int, idx: int, model: str = "gpt-4o-mini", *,
    name: str | None = "planner",
    input_tokens: int = 100, output_tokens: int = 20,
    cost_usd: float = 0.001, metadata: dict[str, Any] | None = None,
) -> ModelCall:
    return ModelCall(
        run_id="r", seq=idx + 100, timestamp=_ts(idx), session_id="s",
        turn_index=turn, call_index=idx, name=name, model=model,
        input_tokens=input_tokens, output_tokens=output_tokens,
        cost_usd=cost_usd, latency_ms=200, metadata=metadata or {},
    )


def _at(turn: int, *, latency_ms: int = 300) -> AgentTurn:
    return AgentTurn(
        run_id="r", seq=900 + turn, timestamp=_ts(turn), session_id="s",
        turn_index=turn, text="ok", latency_ms=latency_ms, fidelity="full",
    )


def _ut(turn: int) -> UserTurn:
    return UserTurn(
        run_id="r", seq=800 + turn, timestamp=_ts(turn),
        session_id="s", turn_index=turn, text="hi",
    )


def test_input_tokens_grew_emits_observed_cause() -> None:
    b: list[Any] = [_ut(0), _mc(0, 0, input_tokens=100), _at(0)]
    c: list[Any] = [_ut(0), _mc(0, 0, input_tokens=200), _at(0)]
    causes = find_causes(b, c, diff(aggregate(b), aggregate(c)))
    descrs = " | ".join(x.description for x in causes)
    assert "input_tokens" in descrs
    assert any(x.confidence == "observed" for x in causes)


def test_output_tokens_grew_emits_observed_cause() -> None:
    b: list[Any] = [_ut(0), _mc(0, 0, output_tokens=20), _at(0)]
    c: list[Any] = [_ut(0), _mc(0, 0, output_tokens=80), _at(0)]
    causes = find_causes(b, c, diff(aggregate(b), aggregate(c)))
    assert any("output_tokens" in x.description for x in causes)


def test_tool_call_count_grew() -> None:
    b: list[Any] = [_ut(0), _tc(0, 0, "get_order", {"id": "1"}), _at(0)]
    c: list[Any] = [
        _ut(0),
        _tc(0, 0, "get_order", {"id": "1"}),
        _tc(0, 1, "get_order", {"id": "2"}),
        _tc(0, 2, "create_label", {"x": 1}),
        _at(0),
    ]
    causes = find_causes(b, c, diff(aggregate(b), aggregate(c)))
    assert any("tool_calls" in x.description for x in causes)


def test_llm_call_count_grew() -> None:
    b: list[Any] = [_ut(0), _mc(0, 0), _at(0)]
    c: list[Any] = [_ut(0), _mc(0, 0), _mc(0, 1), _at(0)]
    causes = find_causes(b, c, diff(aggregate(b), aggregate(c)))
    assert any("llm_calls" in x.description for x in causes)


def test_retry_count_grew() -> None:
    b: list[Any] = [_ut(0), _tc(0, 0, "get_order", {"id": "1"}, retries=0), _at(0)]
    c: list[Any] = [_ut(0), _tc(0, 0, "get_order", {"id": "1"}, retries=4), _at(0)]
    causes = find_causes(b, c, diff(aggregate(b), aggregate(c)))
    assert any("retries" in x.description for x in causes)


def test_repeated_tool_args_correlates() -> None:
    b: list[Any] = [_ut(0), _tc(0, 0, "get_order", {"id": "1"}), _at(0)]
    c: list[Any] = [
        _ut(0),
        _tc(0, 0, "get_order", {"id": "1"}),
        _tc(0, 1, "get_order", {"id": "1"}),
        _tc(0, 2, "get_order", {"id": "1"}),
        _at(0),
    ]
    causes = find_causes(b, c, diff(aggregate(b), aggregate(c)))
    repeats = [c for c in causes if "identical args_hash" in c.description]
    assert len(repeats) == 1
    assert repeats[0].confidence == "correlates"


def test_metadata_changed_correlates() -> None:
    b: list[Any] = [_ut(0), _mc(0, 0, metadata={"rag_chunks": 5}), _at(0)]
    c: list[Any] = [_ut(0), _mc(0, 0, metadata={"rag_chunks": 12}), _at(0)]
    causes = find_causes(b, c, diff(aggregate(b), aggregate(c)))
    metas = [x for x in causes if "metadata.rag_chunks" in x.description]
    assert len(metas) == 1
    assert metas[0].confidence == "correlates"
    assert "5" in metas[0].description and "12" in metas[0].description


def test_model_swapped_is_computed() -> None:
    b: list[Any] = [_ut(0), _mc(0, 0, model="gpt-4o-mini", cost_usd=0.001), _at(0)]
    c: list[Any] = [_ut(0), _mc(0, 0, model="gpt-4o", cost_usd=0.005), _at(0)]
    causes = find_causes(b, c, diff(aggregate(b), aggregate(c)))
    swaps = [x for x in causes if "model swap" in x.description]
    assert len(swaps) == 1
    assert swaps[0].confidence == "computed"
    assert swaps[0].contribution_usd is not None
    assert swaps[0].contribution_usd > 0


def test_per_model_cost_grew() -> None:
    b: list[Any] = [_ut(0), _mc(0, 0, model="m", cost_usd=0.001), _at(0)]
    c: list[Any] = [
        _ut(0),
        _mc(0, 0, model="m", cost_usd=0.001),
        _mc(0, 1, model="m", cost_usd=0.005),
        _at(0),
    ]
    causes = find_causes(b, c, diff(aggregate(b), aggregate(c)))
    per_model = [x for x in causes if "per-model cost grew on m" in x.description]
    assert len(per_model) == 1


def test_no_causes_on_identical_runs() -> None:
    b: list[Any] = [_ut(0), _mc(0, 0), _tc(0, 1, "x", {"a": 1}), _at(0)]
    c: list[Any] = [_ut(0), _mc(0, 0), _tc(0, 1, "x", {"a": 1}), _at(0)]
    causes = find_causes(b, c, diff(aggregate(b), aggregate(c)))
    assert causes == []


def test_causes_never_use_word_caused() -> None:
    """Language hygiene check: no rule output should claim 'caused by'."""
    b: list[Any] = [_ut(0), _mc(0, 0, model="m1"), _at(0)]
    c: list[Any] = [
        _ut(0),
        _mc(0, 0, model="m2", input_tokens=200, output_tokens=80,
            cost_usd=0.005, metadata={"rag_chunks": 12}),
        _tc(0, 1, "x", {"a": 1}, retries=3),
        _tc(0, 2, "x", {"a": 1}),
        _tc(0, 3, "x", {"a": 1}),
        _at(0),
    ]
    causes = find_causes(b, c, diff(aggregate(b), aggregate(c)))
    for c_obj in causes:
        text = c_obj.description.lower()
        assert "caused by" not in text
        assert "is the cause" not in text


def test_causes_ordered_computed_first() -> None:
    b: list[Any] = [_ut(0), _mc(0, 0, model="m1", cost_usd=0.001), _at(0)]
    c: list[Any] = [
        _ut(0),
        _mc(0, 0, model="m2", input_tokens=300, cost_usd=0.005),
        _at(0),
    ]
    causes = find_causes(b, c, diff(aggregate(b), aggregate(c)))
    # The computed model-swap should appear before observed token deltas.
    confidences = [c_obj.confidence for c_obj in causes]
    if "computed" in confidences and "observed" in confidences:
        assert confidences.index("computed") < confidences.index("observed")
