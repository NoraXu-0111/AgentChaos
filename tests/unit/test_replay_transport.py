"""Tests for replay indexing and RecordedTransport."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from agentchaos.profile.metrics import aggregate
from agentchaos.replay.transport import (
    REPLAY_ERROR_PREFIX,
    RecordedTransport,
    index_recording,
)
from agentchaos.runner.session import Session, args_hash
from agentchaos.scenario.schema import AgentTarget, Scenario
from agentchaos.scenario.schema import UserTurn as ScenarioTurn
from agentchaos.trace.reader import read_trace
from agentchaos.trace.recorder import TraceRecorder
from agentchaos.trace.schema import (
    AgentTurn,
    ModelCall,
    RunEnd,
    RunMeta,
    SessionEnd,
    SessionStart,
    ToolCall,
    TraceEvent,
    UserTurn,
)
from agentchaos.transport.base import FidelityTier

_BASE_TS = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)


def _ts(seq: int) -> datetime:
    return _BASE_TS + timedelta(seconds=seq)


def _rec_turn(
    user: str,
    text: str,
    *,
    calls: tuple[tuple[Any, ...], ...] = (),
    error: str | None = None,
    fidelity: str = "full",
    usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One turn spec: calls are ("model",) or ("tool", name, args) in emission order."""
    return {
        "user": user,
        "text": text,
        "calls": calls,
        "error": error,
        "fidelity": fidelity,
        "usage": usage,
    }


def _make_recording(turns: list[dict[str, Any]], run_id: str = "run-rec") -> list[TraceEvent]:
    events: list[TraceEvent] = [
        RunMeta(
            run_id=run_id,
            seq=0,
            timestamp=_ts(0),
            agentchaos_version="0.1.0",
            scenario_path="scenarios/refund.yaml",
            scenario_hash="sha256:abc",
            scenario_name="refund",
            started_at=_ts(0),
        ),
        SessionStart(
            run_id=run_id,
            seq=1,
            timestamp=_ts(1),
            session_id="s-1",
            scenario_name="refund",
            agent_target={"type": "http", "endpoint": "http://localhost:8080/chat"},
        ),
    ]
    seq = 2
    tool_total = 0
    model_total = 0
    for turn_index, turn in enumerate(turns):
        events.append(
            UserTurn(
                run_id=run_id, seq=seq, timestamp=_ts(seq),
                session_id="s-1", turn_index=turn_index, text=turn["user"],
            )
        )
        seq += 1
        for call_index, call in enumerate(turn["calls"]):
            if call[0] == "model":
                model_total += 1
                events.append(
                    ModelCall(
                        run_id=run_id, seq=seq, timestamp=_ts(seq), session_id="s-1",
                        turn_index=turn_index, call_index=call_index, name="planner",
                        model="gpt-4o-mini", input_tokens=100, output_tokens=20,
                        cost_usd=0.001, latency_ms=200, metadata={"rag_chunks": 5},
                    )
                )
            else:
                tool_total += 1
                _, name, args = call
                events.append(
                    ToolCall(
                        run_id=run_id, seq=seq, timestamp=_ts(seq), session_id="s-1",
                        turn_index=turn_index, call_index=call_index, name=name,
                        args=args, args_hash=args_hash(args), latency_ms=50,
                        result_summary="ok", retries=0,
                    )
                )
            seq += 1
        events.append(
            AgentTurn(
                run_id=run_id, seq=seq, timestamp=_ts(seq), session_id="s-1",
                turn_index=turn_index, text=turn["text"], latency_ms=300,
                agent={"name": "refund", "version": "0.1"},
                usage=turn["usage"], fidelity=turn["fidelity"], error=turn["error"],
            )
        )
        seq += 1
    events.append(
        SessionEnd(
            run_id=run_id, seq=seq, timestamp=_ts(seq), session_id="s-1",
            outcome="completed", turns=len(turns), tool_calls=tool_total,
            model_calls=model_total, retries=0, total_cost_usd=0.001 * model_total,
            total_latency_ms=300 * len(turns), duration_s=0.3,
        )
    )
    seq += 1
    events.append(
        RunEnd(
            run_id=run_id, seq=seq, timestamp=_ts(seq), outcome="pass",
            finished_at=_ts(seq), exit_code=0,
        )
    )
    return events


def _two_turn_recording() -> list[TraceEvent]:
    return _make_recording(
        [
            _rec_turn(
                "hi", "order found",
                calls=(("model",), ("tool", "get_order", {"id": "1"})),
            ),
            _rec_turn(
                "return it", "label sent",
                calls=(("tool", "create_return_label", {"id": "1"}),),
            ),
        ]
    )


def _empty_recording() -> list[TraceEvent]:
    return [
        RunMeta(
            run_id="run-e", seq=0, timestamp=_ts(0), agentchaos_version="0.1.0",
            scenario_path="s.yaml", scenario_hash="sha256:abc",
            scenario_name="refund", started_at=_ts(0),
        ),
        RunEnd(
            run_id="run-e", seq=1, timestamp=_ts(1), outcome="pass",
            finished_at=_ts(1), exit_code=0,
        ),
    ]


# ----------------------------------------------------------------------------
# index_recording
# ----------------------------------------------------------------------------


def test_index_recording_groups_turns_in_order() -> None:
    turns = index_recording(_two_turn_recording())
    assert len(turns) == 2
    assert [t.turn_index for t in turns] == [0, 1]
    assert turns[0].user_text == "hi"
    assert turns[1].user_text == "return it"

    events0 = turns[0].result.events
    assert [e["type"] for e in events0] == ["model_call", "tool_call"]
    model = events0[0]
    assert model["name"] == "planner"
    assert model["cost_usd"] == 0.001
    assert model["metadata"] == {"rag_chunks": 5}
    tool = events0[1]
    assert tool["name"] == "get_order"
    assert tool["args"] == {"id": "1"}
    assert tool["metadata"] == {}

    events1 = turns[1].result.events
    assert [e["type"] for e in events1] == ["tool_call"]
    assert events1[0]["name"] == "create_return_label"


def test_index_recording_drops_trailing_user_turn_without_agent_turn() -> None:
    events = _make_recording(
        [_rec_turn("hi", "order found", calls=(("tool", "get_order", {"id": "1"}),))]
    )
    next_seq = max(e.seq for e in events) + 1
    events.append(
        UserTurn(
            run_id="run-rec", seq=next_seq, timestamp=_ts(next_seq),
            session_id="s-1", turn_index=1, text="return it",
        )
    )
    turns = index_recording(events)
    assert len(turns) == 1
    assert turns[0].turn_index == 0


def test_index_recording_empty_trace_returns_empty() -> None:
    assert index_recording(_empty_recording()) == []


def test_index_recording_preserves_error_and_fidelity() -> None:
    events = _make_recording(
        [_rec_turn("hi", "", error="http_500", fidelity="message_only")]
    )
    turns = index_recording(events)
    assert len(turns) == 1
    assert turns[0].result.error == "http_500"
    assert turns[0].result.fidelity == FidelityTier.MESSAGE_ONLY


# ----------------------------------------------------------------------------
# RecordedTransport
# ----------------------------------------------------------------------------


async def test_send_replays_turns_in_sequence() -> None:
    transport = RecordedTransport(_two_turn_recording())
    r0 = await transport.send("s-x", "hi")
    assert r0.text == "order found"
    assert r0.error is None
    assert [e["type"] for e in r0.events] == ["model_call", "tool_call"]
    r1 = await transport.send("s-x", "return it")
    assert r1.text == "label sent"
    assert transport.turns_consumed == 2
    assert transport.turns_total == 2
    assert transport.divergences == []


async def test_send_user_text_mismatch_returns_replay_error() -> None:
    transport = RecordedTransport(_two_turn_recording())
    await transport.send("s-x", "hi")
    result = await transport.send("s-x", "cancel everything")
    assert result.error is not None
    assert result.error.startswith(REPLAY_ERROR_PREFIX)
    assert result.latency_ms == 0
    assert len(transport.divergences) == 1
    d = transport.divergences[0]
    assert d.kind == "user_text_mismatch"
    assert d.turn_index == 1
    assert d.expected == "return it"
    assert d.actual == "cancel everything"


async def test_send_past_end_of_recording_diverges() -> None:
    transport = RecordedTransport(_two_turn_recording())
    await transport.send("s-x", "hi")
    await transport.send("s-x", "return it")
    result = await transport.send("s-x", "one more thing")
    assert result.error is not None
    assert result.error.startswith(REPLAY_ERROR_PREFIX)
    assert len(transport.divergences) == 1
    d = transport.divergences[0]
    assert d.kind == "turn_count_mismatch"
    assert d.turn_index == 2


def test_init_raises_on_recording_with_no_turns() -> None:
    with pytest.raises(ValueError):
        RecordedTransport(_empty_recording())


async def test_send_makes_no_network_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("network call attempted during replay")

    monkeypatch.setattr(httpx.AsyncClient, "__init__", _boom)
    monkeypatch.setattr(httpx.AsyncClient, "post", _boom)

    transport = RecordedTransport(_two_turn_recording())
    r0 = await transport.send("s-x", "hi")
    r1 = await transport.send("s-x", "return it")
    assert r0.error is None and r1.error is None


async def test_replay_through_session_reproduces_metrics(tmp_path: Path) -> None:
    recording = _two_turn_recording()
    scenario = Scenario(
        id="t",
        name="refund",
        agent=AgentTarget(endpoint="http://127.0.0.1:9/chat"),
        conversation=[ScenarioTurn(user="hi"), ScenarioTurn(user="return it")],
    )
    replayed_path = tmp_path / "replayed.jsonl"
    recorder = TraceRecorder(replayed_path)
    session = Session(
        run_id="run-rp",
        session_id="s-rp",
        scenario=scenario,
        transport=RecordedTransport(recording),
        recorder=recorder,
    )
    result = await session.run()
    recorder.close()
    assert result.error is None

    replayed_metrics = aggregate(read_trace(replayed_path))
    recorded_metrics = aggregate(recording)
    assert replayed_metrics.total_cost_usd == recorded_metrics.total_cost_usd
    assert replayed_metrics.tool_calls == recorded_metrics.tool_calls
    assert replayed_metrics.llm_calls == recorded_metrics.llm_calls
    assert replayed_metrics.total_latency_ms == recorded_metrics.total_latency_ms
    assert replayed_metrics.tool_sequence == recorded_metrics.tool_sequence
