"""RecordedTransport — replay agent turns from a prior trace with zero live HTTP."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agentchaos.replay.schema import Divergence
from agentchaos.trace.schema import AgentTurn, ModelCall, ToolCall, TraceEvent, UserTurn
from agentchaos.transport.base import AgentTransport, AgentTurnResult, FidelityTier

REPLAY_ERROR_PREFIX: str = "replay_divergence:"


class RecordedTurn(BaseModel):
    """One recorded user→agent exchange reconstructed from trace events."""

    model_config = ConfigDict(extra="forbid")

    turn_index: int = Field(..., ge=0)
    user_text: str
    result: AgentTurnResult


def _without_none(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


def _model_call_dict(call: ModelCall) -> dict[str, Any]:
    return _without_none(
        {
            "type": "model_call",
            "name": call.name,
            "model": call.model,
            "input_tokens": call.input_tokens,
            "output_tokens": call.output_tokens,
            "cost_usd": call.cost_usd,
            "latency_ms": call.latency_ms,
            "ttft_ms": call.ttft_ms,
            "stop_reason": call.stop_reason,
            "metadata": call.metadata,
        }
    )


def _tool_call_dict(call: ToolCall) -> dict[str, Any]:
    return _without_none(
        {
            "type": "tool_call",
            "name": call.name,
            "args": call.args,
            "latency_ms": call.latency_ms,
            "result_summary": call.result_summary,
            "result_size_bytes": call.result_size_bytes,
            "error": call.error,
            "retries": call.retries,
            "metadata": call.metadata,
        }
    )


def _reconstruct_result(
    agent_turn: AgentTurn, calls: Sequence[ModelCall | ToolCall]
) -> AgentTurnResult:
    """Re-shape a recorded turn back into the HTTP-contract result Session consumes."""
    events: list[dict[str, Any]] = []
    for call in sorted(calls, key=lambda c: c.seq):
        if isinstance(call, ModelCall):
            events.append(_model_call_dict(call))
        else:
            events.append(_tool_call_dict(call))
    return AgentTurnResult(
        text=agent_turn.text,
        events=events,
        usage=agent_turn.usage,
        agent=agent_turn.agent,
        fidelity=FidelityTier(agent_turn.fidelity),
        latency_ms=agent_turn.latency_ms,
        ttft_ms=agent_turn.ttft_ms,
        error=agent_turn.error,
        status_code=None,
    )


def index_recording(events: Sequence[TraceEvent]) -> list[RecordedTurn]:
    """Group a recorded trace into replayable per-turn entries, ordered by turn_index.

    A trailing ``user_turn`` with no matching ``agent_turn`` (crashed recording)
    is dropped; replay of that turn later surfaces as an exhaustion divergence.
    """
    user_texts: dict[int, str] = {}
    calls: dict[int, list[ModelCall | ToolCall]] = {}
    agent_turns: dict[int, AgentTurn] = {}

    for event in sorted(events, key=lambda e: e.seq):
        if isinstance(event, UserTurn):
            user_texts[event.turn_index] = event.text
        elif isinstance(event, ModelCall | ToolCall):
            calls.setdefault(event.turn_index, []).append(event)
        elif isinstance(event, AgentTurn):
            agent_turns[event.turn_index] = event

    turns: list[RecordedTurn] = []
    for turn_index in sorted(agent_turns):
        turns.append(
            RecordedTurn(
                turn_index=turn_index,
                user_text=user_texts.get(turn_index, ""),
                result=_reconstruct_result(agent_turns[turn_index], calls.get(turn_index, [])),
            )
        )
    return turns


class RecordedTransport(AgentTransport):
    """AgentTransport that serves recorded turns instead of making HTTP calls."""

    def __init__(self, recording: Sequence[TraceEvent]) -> None:
        """Index ``recording`` into per-turn results. Raises ValueError if it has no turns."""
        self._turns = index_recording(recording)
        if not self._turns:
            raise ValueError("recording contains no replayable turns")
        self._consumed = 0
        self._divergences: list[Divergence] = []

    @property
    def divergences(self) -> list[Divergence]:
        """Divergences observed live during replay (text mismatch / exhaustion)."""
        return list(self._divergences)

    @property
    def turns_total(self) -> int:
        """Number of replayable turns in the recording."""
        return len(self._turns)

    @property
    def turns_consumed(self) -> int:
        """Number of turns served so far."""
        return self._consumed

    async def send(self, session_id: str, message: str) -> AgentTurnResult:
        """Return the next recorded turn's result; never performs network I/O.

        On user-text mismatch or recording exhaustion, records a Divergence and
        returns an AgentTurnResult whose ``error`` starts with REPLAY_ERROR_PREFIX
        (latency_ms=0) so the Session stops cleanly.
        """
        if self._consumed >= len(self._turns):
            divergence = Divergence(
                kind="turn_count_mismatch",
                turn_index=self._consumed,
                detail=(
                    f"recording exhausted: scenario sent turn {self._consumed} but the "
                    f"recording only has {len(self._turns)} turn(s)"
                ),
                expected=str(len(self._turns)),
                actual=str(self._consumed + 1),
            )
            self._divergences.append(divergence)
            return AgentTurnResult(
                text="",
                latency_ms=0,
                error=f"{REPLAY_ERROR_PREFIX} {divergence.detail}",
            )

        turn = self._turns[self._consumed]
        if message != turn.user_text:
            divergence = Divergence(
                kind="user_text_mismatch",
                turn_index=turn.turn_index,
                detail=f"turn {turn.turn_index}: user text differs from the recording",
                expected=turn.user_text,
                actual=message,
            )
            self._divergences.append(divergence)
            return AgentTurnResult(
                text="",
                latency_ms=0,
                error=f"{REPLAY_ERROR_PREFIX} {divergence.detail}",
            )

        self._consumed += 1
        return turn.result
