"""Pure trace-vs-trace replay divergence detection (no I/O, no network)."""
from __future__ import annotations

from collections.abc import Iterable, Sequence

from pydantic import BaseModel, ConfigDict, Field

from agentchaos.replay.schema import Divergence
from agentchaos.trace.schema import AgentTurn, ModelCall, ToolCall, TraceEvent, UserTurn
from agentchaos.violations import Violation

_REPLAY_SENTINEL_PREFIX = "replay_divergence:"


class TurnBehavior(BaseModel):
    """Normalized, order-preserving view of one turn's observable behavior."""

    model_config = ConfigDict(extra="forbid")

    turn_index: int = Field(..., ge=0)
    user_text: str
    tool_calls: list[tuple[str, str]] = Field(default_factory=list)  # (name, args_hash)
    model_call_count: int = 0
    agent_text: str = ""
    agent_error: str | None = None


def extract_behavior(events: Iterable[TraceEvent]) -> list[TurnBehavior]:
    """Reduce a trace to per-turn behavior views, ordered by turn_index.

    A trailing ``user_turn`` with no matching ``agent_turn`` (crash-truncated
    recording) is dropped, mirroring ``index_recording``.
    """
    user_texts: dict[int, str] = {}
    tool_calls: dict[int, list[tuple[str, str]]] = {}
    model_counts: dict[int, int] = {}
    agent_turns: dict[int, AgentTurn] = {}

    for event in sorted(events, key=lambda e: e.seq):
        if isinstance(event, UserTurn):
            user_texts[event.turn_index] = event.text
        elif isinstance(event, ToolCall):
            tool_calls.setdefault(event.turn_index, []).append((event.name, event.args_hash))
        elif isinstance(event, ModelCall):
            model_counts[event.turn_index] = model_counts.get(event.turn_index, 0) + 1
        elif isinstance(event, AgentTurn):
            agent_turns[event.turn_index] = event

    behaviors: list[TurnBehavior] = []
    for turn_index in sorted(agent_turns):
        agent_turn = agent_turns[turn_index]
        behaviors.append(
            TurnBehavior(
                turn_index=turn_index,
                user_text=user_texts.get(turn_index, ""),
                tool_calls=tool_calls.get(turn_index, []),
                model_call_count=model_counts.get(turn_index, 0),
                agent_text=agent_turn.text,
                agent_error=agent_turn.error,
            )
        )
    return behaviors


def _render_call(call: tuple[str, str]) -> str:
    name, hash_ = call
    return f"{name}({hash_})"


def _compare_tool_calls(recorded: TurnBehavior, candidate: TurnBehavior) -> Divergence | None:
    """Positional comparison over (name, args_hash) pairs; first mismatch wins."""
    for position, (rec_call, cand_call) in enumerate(
        zip(recorded.tool_calls, candidate.tool_calls, strict=False)
    ):
        if rec_call != cand_call:
            return Divergence(
                kind="tool_call_mismatch",
                turn_index=recorded.turn_index,
                detail=(
                    f"turn {recorded.turn_index}: tool call {position} differs — "
                    f"expected {_render_call(rec_call)}, got {_render_call(cand_call)}"
                ),
                expected=_render_call(rec_call),
                actual=_render_call(cand_call),
            )
    if len(candidate.tool_calls) > len(recorded.tool_calls):
        extra = candidate.tool_calls[len(recorded.tool_calls)]
        return Divergence(
            kind="extra_tool_call",
            turn_index=recorded.turn_index,
            detail=(
                f"turn {recorded.turn_index}: candidate made an extra tool call "
                f"{_render_call(extra)}"
            ),
            expected=None,
            actual=_render_call(extra),
        )
    if len(candidate.tool_calls) < len(recorded.tool_calls):
        missing = recorded.tool_calls[len(candidate.tool_calls)]
        return Divergence(
            kind="missing_tool_call",
            turn_index=recorded.turn_index,
            detail=(
                f"turn {recorded.turn_index}: candidate skipped recorded tool call "
                f"{_render_call(missing)}"
            ),
            expected=_render_call(missing),
            actual=None,
        )
    return None


def _compare_turn(recorded: TurnBehavior, candidate: TurnBehavior) -> Divergence | None:
    """First mismatch wins: user_text → tool sequence → model count → agent text."""
    if recorded.user_text != candidate.user_text:
        return Divergence(
            kind="user_text_mismatch",
            turn_index=recorded.turn_index,
            detail=f"turn {recorded.turn_index}: user text differs from the recording",
            expected=recorded.user_text,
            actual=candidate.user_text,
        )
    tool_divergence = _compare_tool_calls(recorded, candidate)
    if tool_divergence is not None:
        return tool_divergence
    if recorded.model_call_count != candidate.model_call_count:
        return Divergence(
            kind="model_call_count_mismatch",
            turn_index=recorded.turn_index,
            detail=(
                f"turn {recorded.turn_index}: model call count differs — expected "
                f"{recorded.model_call_count}, got {candidate.model_call_count}"
            ),
            expected=str(recorded.model_call_count),
            actual=str(candidate.model_call_count),
        )
    candidate_diverged_upstream = candidate.agent_error is not None and (
        candidate.agent_error.startswith(_REPLAY_SENTINEL_PREFIX)
    )
    if not candidate_diverged_upstream and recorded.agent_text != candidate.agent_text:
        return Divergence(
            kind="agent_text_mismatch",
            turn_index=recorded.turn_index,
            detail=f"turn {recorded.turn_index}: agent response text differs from the recording",
            expected=recorded.agent_text,
            actual=candidate.agent_text,
        )
    return None


def detect_replay_divergence(
    recording: Iterable[TraceEvent],
    candidate: Iterable[TraceEvent],
) -> list[Divergence]:
    """Compare candidate behavior to the recording.

    Reports at most one Divergence per turn (first mismatch wins, in order:
    user_text → tool sequence → model_call_count → agent_text) plus at most one
    turn_count_mismatch for the whole pair. Two empty traces → [].
    """
    recorded_turns = extract_behavior(recording)
    candidate_turns = extract_behavior(candidate)

    divergences: list[Divergence] = []
    for recorded_turn, candidate_turn in zip(recorded_turns, candidate_turns, strict=False):
        divergence = _compare_turn(recorded_turn, candidate_turn)
        if divergence is not None:
            divergences.append(divergence)

    if len(recorded_turns) != len(candidate_turns):
        divergences.append(
            Divergence(
                kind="turn_count_mismatch",
                turn_index=min(len(recorded_turns), len(candidate_turns)),
                detail=(
                    f"turn count differs — recording has {len(recorded_turns)} turn(s), "
                    f"candidate has {len(candidate_turns)}"
                ),
                expected=str(len(recorded_turns)),
                actual=str(len(candidate_turns)),
            )
        )
    return divergences


def divergences_to_violations(divergences: Sequence[Divergence]) -> list[Violation]:
    """Map each Divergence to a Violation(kind='replay', name=<kind>, detail=<detail>)."""
    return [
        Violation(kind="replay", name=d.kind, detail=d.detail) for d in divergences
    ]
