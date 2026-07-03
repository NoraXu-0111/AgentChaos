"""Tests for trace-vs-trace replay divergence detection and violation mapping."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from agentchaos.replay.detect import (
    detect_replay_divergence,
    divergences_to_violations,
    extract_behavior,
)
from agentchaos.replay.schema import Divergence
from agentchaos.runner.session import args_hash
from agentchaos.trace.schema import (
    AgentTurn,
    ModelCall,
    RunMeta,
    ToolCall,
    TraceEvent,
    UserTurn,
)

_BASE_TS = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)


def _ts(seq: int) -> datetime:
    return _BASE_TS + timedelta(seconds=seq)


def _turn(
    user: str,
    text: str,
    *,
    tools: tuple[tuple[str, dict[str, Any]], ...] = (),
    model_calls: int = 1,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "user": user,
        "text": text,
        "tools": tools,
        "model_calls": model_calls,
        "error": error,
    }


def _make_trace(turns: list[dict[str, Any]], run_id: str = "run-a") -> list[TraceEvent]:
    events: list[TraceEvent] = [
        RunMeta(
            run_id=run_id, seq=0, timestamp=_ts(0), agentchaos_version="0.1.0",
            scenario_path="s.yaml", scenario_hash="sha256:abc",
            scenario_name="refund", started_at=_ts(0),
        )
    ]
    seq = 1
    for turn_index, turn in enumerate(turns):
        events.append(
            UserTurn(
                run_id=run_id, seq=seq, timestamp=_ts(seq),
                session_id="s-1", turn_index=turn_index, text=turn["user"],
            )
        )
        seq += 1
        call_index = 0
        for _ in range(turn["model_calls"]):
            events.append(
                ModelCall(
                    run_id=run_id, seq=seq, timestamp=_ts(seq), session_id="s-1",
                    turn_index=turn_index, call_index=call_index,
                    model="gpt-4o-mini", cost_usd=0.001, latency_ms=200,
                )
            )
            seq += 1
            call_index += 1
        for name, args in turn["tools"]:
            events.append(
                ToolCall(
                    run_id=run_id, seq=seq, timestamp=_ts(seq), session_id="s-1",
                    turn_index=turn_index, call_index=call_index, name=name,
                    args=args, args_hash=args_hash(args), latency_ms=50,
                    result_summary="ok", retries=0,
                )
            )
            seq += 1
            call_index += 1
        events.append(
            AgentTurn(
                run_id=run_id, seq=seq, timestamp=_ts(seq), session_id="s-1",
                turn_index=turn_index, text=turn["text"], latency_ms=300,
                error=turn["error"],
            )
        )
        seq += 1
    return events


def _base_turns() -> list[dict[str, Any]]:
    return [
        _turn(
            "hi", "order found",
            tools=(("get_order", {"id": "1"}),),
        ),
        _turn(
            "return it", "label sent",
            tools=(("create_return_label", {"id": "1"}),),
        ),
    ]


# ----------------------------------------------------------------------------
# extract_behavior
# ----------------------------------------------------------------------------


def test_extract_behavior_orders_turns_and_tool_calls() -> None:
    trace = _make_trace(
        [
            _turn(
                "hi", "done",
                tools=(("get_order", {"id": "1"}), ("create_return_label", {"id": "1"})),
            ),
            _turn("thanks", "bye", tools=()),
        ]
    )
    behaviors = extract_behavior(trace)
    assert [b.turn_index for b in behaviors] == [0, 1]
    assert behaviors[0].user_text == "hi"
    assert behaviors[0].tool_calls == [
        ("get_order", args_hash({"id": "1"})),
        ("create_return_label", args_hash({"id": "1"})),
    ]
    assert behaviors[1].tool_calls == []
    assert behaviors[1].agent_text == "bye"


def test_extract_behavior_empty_trace() -> None:
    assert extract_behavior([]) == []


def test_extract_behavior_captures_agent_error_and_model_count() -> None:
    trace = _make_trace([_turn("hi", "", model_calls=2, error="http_500")])
    behaviors = extract_behavior(trace)
    assert len(behaviors) == 1
    assert behaviors[0].model_call_count == 2
    assert behaviors[0].agent_error == "http_500"


# ----------------------------------------------------------------------------
# detect_replay_divergence
# ----------------------------------------------------------------------------


def test_identical_traces_no_divergence() -> None:
    recording = _make_trace(_base_turns(), run_id="run-a")
    candidate = _make_trace(_base_turns(), run_id="run-b")
    assert detect_replay_divergence(recording, candidate) == []


def test_extra_candidate_tool_call() -> None:
    recording = _make_trace(_base_turns())
    changed = _base_turns()
    changed[1]["tools"] = (
        ("create_return_label", {"id": "1"}),
        ("send_email", {"to": "x"}),
    )
    candidate = _make_trace(changed, run_id="run-b")
    divergences = detect_replay_divergence(recording, candidate)
    assert len(divergences) == 1
    assert divergences[0].kind == "extra_tool_call"
    assert divergences[0].turn_index == 1
    assert "send_email" in (divergences[0].actual or "")


def test_missing_candidate_tool_call() -> None:
    recording = _make_trace(_base_turns())
    changed = _base_turns()
    changed[1]["tools"] = ()
    candidate = _make_trace(changed, run_id="run-b")
    divergences = detect_replay_divergence(recording, candidate)
    assert len(divergences) == 1
    assert divergences[0].kind == "missing_tool_call"
    assert divergences[0].turn_index == 1
    assert "create_return_label" in (divergences[0].expected or "")


def test_args_hash_mismatch_is_tool_call_mismatch() -> None:
    recording = _make_trace(_base_turns())
    changed = _base_turns()
    changed[0]["tools"] = (("get_order", {"id": "999"}),)
    candidate = _make_trace(changed, run_id="run-b")
    divergences = detect_replay_divergence(recording, candidate)
    assert len(divergences) == 1
    d = divergences[0]
    assert d.kind == "tool_call_mismatch"
    assert d.turn_index == 0
    assert d.expected == f"get_order({args_hash({'id': '1'})})"
    assert d.actual == f"get_order({args_hash({'id': '999'})})"


def test_tool_order_swap_reports_first_position() -> None:
    base = [_turn("hi", "done", tools=(("a", {"x": 1}), ("b", {"y": 2})))]
    swapped = [_turn("hi", "done", tools=(("b", {"y": 2}), ("a", {"x": 1})))]
    divergences = detect_replay_divergence(
        _make_trace(base), _make_trace(swapped, run_id="run-b")
    )
    assert len(divergences) == 1
    assert divergences[0].kind == "tool_call_mismatch"
    assert "tool call 0" in divergences[0].detail


def test_candidate_missing_whole_turn() -> None:
    recording = _make_trace(_base_turns())
    candidate = _make_trace(_base_turns()[:1], run_id="run-b")
    divergences = detect_replay_divergence(recording, candidate)
    assert len(divergences) == 1
    d = divergences[0]
    assert d.kind == "turn_count_mismatch"
    assert d.expected == "2"
    assert d.actual == "1"


def test_user_text_mismatch_wins_over_tool_mismatch() -> None:
    recording = _make_trace(_base_turns())
    changed = _base_turns()
    changed[1]["user"] = "actually cancel it"
    changed[1]["tools"] = (("cancel_order", {"id": "1"}),)
    candidate = _make_trace(changed, run_id="run-b")
    divergences = detect_replay_divergence(recording, candidate)
    assert len(divergences) == 1
    assert divergences[0].kind == "user_text_mismatch"


def test_model_call_count_mismatch_detected() -> None:
    recording = _make_trace(_base_turns())
    changed = _base_turns()
    changed[0]["model_calls"] = 3
    candidate = _make_trace(changed, run_id="run-b")
    divergences = detect_replay_divergence(recording, candidate)
    assert len(divergences) == 1
    d = divergences[0]
    assert d.kind == "model_call_count_mismatch"
    assert d.expected == "1"
    assert d.actual == "3"


def test_agent_text_mismatch_detected() -> None:
    recording = _make_trace(_base_turns())
    changed = _base_turns()
    changed[1]["text"] = "sorry, something went wrong"
    candidate = _make_trace(changed, run_id="run-b")
    divergences = detect_replay_divergence(recording, candidate)
    assert len(divergences) == 1
    d = divergences[0]
    assert d.kind == "agent_text_mismatch"
    assert d.expected == "label sent"
    assert d.actual == "sorry, something went wrong"


def test_both_empty_traces_no_divergence() -> None:
    assert detect_replay_divergence([], []) == []


# ----------------------------------------------------------------------------
# divergences_to_violations
# ----------------------------------------------------------------------------


def test_maps_kind_name_detail() -> None:
    d = Divergence(kind="agent_text_mismatch", turn_index=0, detail="turn 0: text differs")
    violations = divergences_to_violations([d])
    assert len(violations) == 1
    assert violations[0].kind == "replay"
    assert violations[0].name == "agent_text_mismatch"
    assert violations[0].detail == "turn 0: text differs"


def test_empty_list_maps_to_empty() -> None:
    assert divergences_to_violations([]) == []


def test_order_preserved() -> None:
    divergences = [
        Divergence(kind="user_text_mismatch", turn_index=0, detail="d0"),
        Divergence(kind="tool_call_mismatch", turn_index=1, detail="d1"),
        Divergence(kind="turn_count_mismatch", turn_index=2, detail="d2"),
    ]
    violations = divergences_to_violations(divergences)
    assert [v.name for v in violations] == [
        "user_text_mismatch", "tool_call_mismatch", "turn_count_mismatch",
    ]
