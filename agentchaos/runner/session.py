"""One multi-turn conversation against an agent."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from agentchaos.scenario.schema import Scenario
from agentchaos.seq import SeqCounter
from agentchaos.trace.recorder import TraceRecorder
from agentchaos.trace.schema import (
    AgentTurn,
    ModelCall,
    SessionEnd,
    SessionStart,
    ToolCall,
    UserTurn,
)
from agentchaos.transport.base import AgentTransport, FidelityTier


def args_hash(args: dict[str, Any]) -> str:
    """Stable, canonical hash of tool call args. 16 hex chars (not for security)."""
    canonical = json.dumps(args, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"sha256:{digest}"


class SessionResult(BaseModel):
    """Summary of one session for reporting and verdict computation."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    outcome: str  # "completed" | "error" | "max_turns_reached"
    turns: int
    tool_calls: int
    model_calls: int
    retries: int
    total_cost_usd: float | None
    total_latency_ms: int
    max_turn_latency_ms: int
    duration_s: float
    fidelity: FidelityTier
    final_text: str
    error: str | None = None


class Session:
    """Drive a multi-turn conversation through a transport and write a trace."""

    def __init__(
        self,
        run_id: str,
        session_id: str,
        scenario: Scenario,
        transport: AgentTransport,
        recorder: TraceRecorder,
        next_seq: int = 1,
        seq: SeqCounter | None = None,
    ) -> None:
        self._run_id = run_id
        self._session_id = session_id
        self._scenario = scenario
        self._transport = transport
        self._recorder = recorder
        self._seq = seq if seq is not None else SeqCounter(start=next_seq)

    def _take_seq(self) -> int:
        return self._seq.take()

    @property
    def next_seq(self) -> int:
        return self._seq.value

    async def run(self) -> SessionResult:
        t_start = time.perf_counter()
        scenario = self._scenario

        # session_start
        self._recorder.write(
            SessionStart(
                run_id=self._run_id,
                seq=self._take_seq(),
                timestamp=datetime.now(UTC),
                session_id=self._session_id,
                scenario_name=scenario.name,
                agent_target={
                    "type": scenario.agent.type,
                    "endpoint": str(scenario.agent.endpoint),
                    "timeout_s": scenario.agent.timeout_s,
                },
            )
        )

        total_cost: float | None = 0.0
        total_latency_ms = 0
        max_turn_latency_ms = 0
        tool_call_count = 0
        model_call_count = 0
        retry_count = 0
        fidelity = FidelityTier.FULL
        last_text = ""
        outcome = "completed"
        error: str | None = None

        for turn_index, turn in enumerate(scenario.conversation):
            # user_turn
            self._recorder.write(
                UserTurn(
                    run_id=self._run_id,
                    seq=self._take_seq(),
                    timestamp=datetime.now(UTC),
                    session_id=self._session_id,
                    turn_index=turn_index,
                    text=turn.user,
                )
            )

            result = await self._transport.send(self._session_id, turn.user)

            # Track aggregate metrics first.
            total_latency_ms += result.latency_ms
            max_turn_latency_ms = max(max_turn_latency_ms, result.latency_ms)
            if result.fidelity != FidelityTier.FULL:
                # Worst-tier wins.
                if fidelity == FidelityTier.FULL:
                    fidelity = result.fidelity
                elif (
                    fidelity == FidelityTier.AGGREGATE
                    and result.fidelity == FidelityTier.MESSAGE_ONLY
                ):
                    fidelity = FidelityTier.MESSAGE_ONLY

            # Walk events emitted by the agent and write typed events for each.
            call_index = 0
            for ev in result.events:
                ev_type = ev.get("type")
                if ev_type == "model_call":
                    model_call_count += 1
                    cost = _maybe_float(ev.get("cost_usd"))
                    if cost is not None and total_cost is not None:
                        total_cost += cost
                    self._recorder.write(
                        ModelCall(
                            run_id=self._run_id,
                            seq=self._take_seq(),
                            timestamp=datetime.now(UTC),
                            session_id=self._session_id,
                            turn_index=turn_index,
                            call_index=call_index,
                            name=ev.get("name"),
                            model=str(ev.get("model", "unknown")),
                            input_tokens=_maybe_int(ev.get("input_tokens")),
                            output_tokens=_maybe_int(ev.get("output_tokens")),
                            cost_usd=cost,
                            latency_ms=_maybe_int(ev.get("latency_ms")),
                            ttft_ms=_maybe_int(ev.get("ttft_ms")),
                            stop_reason=ev.get("stop_reason"),
                            metadata=_dict(ev.get("metadata")),
                        )
                    )
                    call_index += 1
                elif ev_type == "tool_call":
                    tool_call_count += 1
                    retries = _maybe_int(ev.get("retries")) or 0
                    retry_count += retries
                    raw_args = _dict(ev.get("args"))
                    self._recorder.write(
                        ToolCall(
                            run_id=self._run_id,
                            seq=self._take_seq(),
                            timestamp=datetime.now(UTC),
                            session_id=self._session_id,
                            turn_index=turn_index,
                            call_index=call_index,
                            name=str(ev.get("name", "unknown")),
                            args=raw_args,
                            args_hash=args_hash(raw_args),
                            latency_ms=_maybe_int(ev.get("latency_ms")),
                            result_summary=_safe_summary(ev.get("result_summary")),
                            result_size_bytes=_maybe_int(ev.get("result_size_bytes")),
                            error=ev.get("error"),
                            retries=retries,
                            metadata=_dict(ev.get("metadata")),
                        )
                    )
                    call_index += 1

            # If the response carried top-level usage and we never saw a model_call
            # (aggregate fidelity), attribute its cost to the run total.
            if result.fidelity != FidelityTier.FULL and result.usage is not None:
                cost = _maybe_float(result.usage.get("cost_usd"))
                if cost is not None and total_cost is not None:
                    total_cost += cost

            if result.fidelity == FidelityTier.MESSAGE_ONLY:
                # Cost and tokens are unknown.
                total_cost = None

            # agent_turn (always written, even on error)
            self._recorder.write(
                AgentTurn(
                    run_id=self._run_id,
                    seq=self._take_seq(),
                    timestamp=datetime.now(UTC),
                    session_id=self._session_id,
                    turn_index=turn_index,
                    text=result.text,
                    latency_ms=result.latency_ms,
                    ttft_ms=result.ttft_ms,
                    agent=result.agent,
                    usage=result.usage,
                    fidelity=result.fidelity.value,
                    error=result.error,
                )
            )
            last_text = result.text

            if result.error is not None:
                outcome = "error"
                error = result.error
                break

        duration_s = time.perf_counter() - t_start
        final_turns = len(scenario.conversation) if outcome != "error" else turn_index + 1
        session_outcome: Any = outcome
        self._recorder.write(
            SessionEnd(
                run_id=self._run_id,
                seq=self._take_seq(),
                timestamp=datetime.now(UTC),
                session_id=self._session_id,
                outcome=session_outcome,
                turns=final_turns,
                tool_calls=tool_call_count,
                model_calls=model_call_count,
                retries=retry_count,
                total_cost_usd=total_cost,
                total_latency_ms=total_latency_ms,
                duration_s=duration_s,
            )
        )

        return SessionResult(
            session_id=self._session_id,
            outcome=outcome,
            turns=final_turns,
            tool_calls=tool_call_count,
            model_calls=model_call_count,
            retries=retry_count,
            total_cost_usd=total_cost,
            total_latency_ms=total_latency_ms,
            max_turn_latency_ms=max_turn_latency_ms,
            duration_s=duration_s,
            fidelity=fidelity,
            final_text=last_text,
            error=error,
        )


def _maybe_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _maybe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _dict(v: Any) -> dict[str, Any]:
    if isinstance(v, dict):
        return v
    return {}


def _safe_summary(v: Any) -> Any:
    if v in ("ok", "error", "malformed"):
        return v
    return None
