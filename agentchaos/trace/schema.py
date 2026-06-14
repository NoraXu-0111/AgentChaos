"""Pydantic discriminated union for trace events.

Schema version 1. JSONL with one event per line. ``run_meta`` is always first.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Field, TypeAdapter

SCHEMA_VERSION: Literal["1"] = "1"


class _BaseEvent(BaseModel):
    """Fields shared by every event."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = SCHEMA_VERSION
    run_id: str
    seq: int = Field(..., ge=0)
    timestamp: datetime
    session_id: str | None = None


class RunMeta(_BaseEvent):
    kind: Literal["run_meta"] = "run_meta"
    agentchaos_version: str
    scenario_path: str
    scenario_hash: str
    scenario_name: str
    seed: int | None = None
    git_sha: str | None = None
    started_at: datetime


class SessionStart(_BaseEvent):
    kind: Literal["session_start"] = "session_start"
    scenario_name: str
    agent_target: dict[str, Any]


class UserTurn(_BaseEvent):
    kind: Literal["user_turn"] = "user_turn"
    turn_index: int = Field(..., ge=0)
    text: str


class AgentTurn(_BaseEvent):
    kind: Literal["agent_turn"] = "agent_turn"
    turn_index: int = Field(..., ge=0)
    text: str
    latency_ms: int = Field(..., ge=0)
    ttft_ms: int | None = None
    agent: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
    fidelity: Literal["full", "aggregate", "message_only"] = "full"
    error: str | None = None


class ModelCall(_BaseEvent):
    kind: Literal["model_call"] = "model_call"
    turn_index: int = Field(..., ge=0)
    call_index: int = Field(..., ge=0)
    name: str | None = None
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None
    ttft_ms: int | None = None
    stop_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    parent_seq: int | None = None


class ToolCall(_BaseEvent):
    kind: Literal["tool_call"] = "tool_call"
    turn_index: int = Field(..., ge=0)
    call_index: int = Field(..., ge=0)
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    args_hash: str
    latency_ms: int | None = None
    result_summary: Literal["ok", "error", "malformed"] | None = None
    result_size_bytes: int | None = None
    error: str | None = None
    retries: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    parent_seq: int | None = None


class ChaosInjected(_BaseEvent):
    kind: Literal["chaos_injected"] = "chaos_injected"
    target: str
    policy: str
    injection_type: Literal["status_code", "latency"]
    value: int = Field(..., ge=0)
    tool_name: str
    args_hash: str | None = None


class ToolResponse(_BaseEvent):
    kind: Literal["tool_response"] = "tool_response"
    tool_name: str
    status: int = Field(..., ge=0)
    size_bytes: int = Field(..., ge=0)
    headers_subset: dict[str, str] = Field(default_factory=dict)
    body: dict[str, Any] | None = None
    chaos_injected: bool = False
    args_hash: str | None = None


class Retry(_BaseEvent):
    kind: Literal["retry"] = "retry"
    turn_index: int = Field(..., ge=0)
    logical_call_index: int = Field(..., ge=0)
    attempt: int = Field(..., ge=1)
    reason: str | None = None
    backoff_ms: int | None = None


class SessionEnd(_BaseEvent):
    kind: Literal["session_end"] = "session_end"
    outcome: Literal["completed", "error", "max_turns_reached"]
    turns: int = Field(..., ge=0)
    tool_calls: int = Field(..., ge=0)
    model_calls: int = Field(..., ge=0)
    retries: int = Field(..., ge=0)
    total_cost_usd: float | None = None
    total_latency_ms: int = Field(..., ge=0)
    duration_s: float = Field(..., ge=0)


class RunEnd(_BaseEvent):
    kind: Literal["run_end"] = "run_end"
    outcome: Literal["pass", "fail"]
    finished_at: datetime
    exit_code: int


TraceEvent = Annotated[
    RunMeta
    | SessionStart
    | UserTurn
    | AgentTurn
    | ModelCall
    | ToolCall
    | ChaosInjected
    | ToolResponse
    | Retry
    | SessionEnd
    | RunEnd,
    Discriminator("kind"),
]

_ADAPTER: TypeAdapter[TraceEvent] = TypeAdapter(TraceEvent)


def parse_event(data: dict[str, Any]) -> TraceEvent:
    """Validate a raw dict into the appropriate TraceEvent subclass."""
    return _ADAPTER.validate_python(data)
