"""Pure mapping from trace events to backend-agnostic span specs.

No opentelemetry imports — this module works without the [otel] extra installed.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agentchaos.trace.schema import (
    AgentTurn,
    ChaosInjected,
    ModelCall,
    Retry,
    RunEnd,
    RunMeta,
    SessionEnd,
    SessionStart,
    ToolCall,
    ToolResponse,
    TraceEvent,
    UserTurn,
)

AttrValue = str | int | float | bool | list[str]

GEN_AI_COST_USD_ATTR: str = "agentchaos.cost_usd"
GEN_AI_TOTAL_COST_USD_ATTR: str = "agentchaos.total_cost_usd"


class SpanBuildError(Exception):
    """Raised when a trace cannot be mapped to spans (e.g. no run_meta event)."""


class SpanEventSpec(BaseModel):
    """A point-in-time OTel span event (name + nanosecond timestamp + attributes)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    time_unix_nano: int = Field(..., ge=0)
    attributes: dict[str, AttrValue] = Field(default_factory=dict)


class SpanSpec(BaseModel):
    """Backend-agnostic description of one OTel span derived from trace events."""

    model_config = ConfigDict(extra="forbid")

    spec_id: int
    parent_id: int | None = None
    name: str
    kind: Literal["internal", "client"] = "internal"
    start_time_unix_nano: int = Field(..., ge=0)
    end_time_unix_nano: int = Field(..., ge=0)
    attributes: dict[str, AttrValue] = Field(default_factory=dict)
    status: Literal["unset", "error"] = "unset"
    status_description: str | None = None
    events: list[SpanEventSpec] = Field(default_factory=list)


_SYSTEM_PREFIXES: tuple[tuple[str, str], ...] = (
    ("gpt-", "openai"),
    ("o1", "openai"),
    ("o3", "openai"),
    ("o4", "openai"),
    ("claude", "anthropic"),
    ("gemini", "gcp.gemini"),
    ("llama", "meta"),
    ("mistral", "mistral_ai"),
    ("mixtral", "mistral_ai"),
)


def infer_gen_ai_system(model: str) -> str:
    """Best-effort gen_ai.system provider from a model name; falls back to 'unknown'."""
    lowered = model.lower()
    for prefix, system in _SYSTEM_PREFIXES:
        if lowered.startswith(prefix):
            return system
    return "unknown"


def _ns(ts: datetime) -> int:
    """Datetime -> unix nanoseconds; naive datetimes are treated as UTC."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return int(ts.timestamp() * 1_000_000_000)


def _attrs(pairs: dict[str, AttrValue | None]) -> dict[str, AttrValue]:
    """Drop attributes whose source value is None (never emit null attributes)."""
    return {k: v for k, v in pairs.items() if v is not None}


def _leaf_start(end_ns: int, latency_ms: int | None) -> int:
    """Start time for a latency-derived leaf span, clamped so start <= end."""
    if latency_ms is None:
        return end_ns
    return min(end_ns, end_ns - latency_ms * 1_000_000)


class _OpenTurn:
    """Bookkeeping for a turn span that has not been closed yet."""

    def __init__(self, spec: SpanSpec, turn_index: int) -> None:
        self.spec = spec
        self.turn_index = turn_index
        self.max_child_end_ns: int | None = None


def _root_span(meta: RunMeta) -> SpanSpec:
    start = _ns(meta.started_at)
    return SpanSpec(
        spec_id=0,
        parent_id=None,
        name=f"agentchaos.run {meta.scenario_name}",
        kind="internal",
        start_time_unix_nano=start,
        end_time_unix_nano=start,
        attributes=_attrs(
            {
                "agentchaos.run_id": meta.run_id,
                "agentchaos.version": meta.agentchaos_version,
                "agentchaos.scenario.name": meta.scenario_name,
                "agentchaos.scenario.path": meta.scenario_path,
                "agentchaos.scenario.hash": meta.scenario_hash,
                "agentchaos.seed": meta.seed,
                "agentchaos.git_sha": meta.git_sha,
            }
        ),
    )


class _Builder:
    """Single-pass trace-events -> SpanSpecs accumulator."""

    def __init__(self) -> None:
        self.specs: list[SpanSpec] = []
        self.root: SpanSpec | None = None
        self.open_turn: _OpenTurn | None = None
        self.max_end_ns: int = 0
        self.root_closed: bool = False

    def _next_id(self) -> int:
        return len(self.specs)

    def _require_root(self) -> SpanSpec:
        if self.root is None:
            raise SpanBuildError("trace contains no run_meta event")
        return self.root

    def _track_end(self, end_ns: int) -> None:
        self.max_end_ns = max(self.max_end_ns, end_ns)
        if self.open_turn is not None:
            prior = self.open_turn.max_child_end_ns
            self.open_turn.max_child_end_ns = end_ns if prior is None else max(prior, end_ns)

    def _close_turn(self, end_ns: int | None) -> None:
        """Close the open turn at end_ns, or at its max child end when end_ns is None."""
        turn = self.open_turn
        if turn is None:
            return
        if end_ns is None:
            end_ns = (
                turn.max_child_end_ns
                if turn.max_child_end_ns is not None
                else turn.spec.start_time_unix_nano
            )
        turn.spec.end_time_unix_nano = max(end_ns, turn.spec.start_time_unix_nano)
        self.max_end_ns = max(self.max_end_ns, turn.spec.end_time_unix_nano)
        self.open_turn = None

    def _add_leaf(self, spec: SpanSpec) -> None:
        self.specs.append(spec)
        self._track_end(spec.end_time_unix_nano)

    def _current_parent(self) -> SpanSpec:
        if self.open_turn is not None:
            return self.open_turn.spec
        return self._require_root()

    # -- per-event handlers ----------------------------------------------

    def on_run_meta(self, ev: RunMeta) -> None:
        if self.root is not None:
            return
        self.root = _root_span(ev)
        self.specs.append(self.root)

    def on_session_start(self, ev: SessionStart) -> None:
        t = _ns(ev.timestamp)
        self._require_root().events.append(
            SpanEventSpec(
                name="session_start",
                time_unix_nano=t,
                attributes={"agentchaos.scenario.name": ev.scenario_name},
            )
        )
        self.max_end_ns = max(self.max_end_ns, t)

    def on_user_turn(self, ev: UserTurn) -> None:
        root = self._require_root()
        start = _ns(ev.timestamp)
        self._close_turn(start)
        spec = SpanSpec(
            spec_id=self._next_id(),
            parent_id=root.spec_id,
            name=f"turn {ev.turn_index}",
            kind="internal",
            start_time_unix_nano=start,
            end_time_unix_nano=start,
            attributes=_attrs(
                {
                    "agentchaos.turn_index": ev.turn_index,
                    "gen_ai.conversation.id": ev.session_id,
                }
            ),
        )
        self.specs.append(spec)
        self.open_turn = _OpenTurn(spec, ev.turn_index)

    def on_agent_turn(self, ev: AgentTurn) -> None:
        self._require_root()
        turn = self.open_turn
        if turn is None or turn.turn_index != ev.turn_index:
            return
        usage = ev.usage or {}
        turn.spec.attributes.update(
            _attrs(
                {
                    "agentchaos.latency_ms": ev.latency_ms,
                    "agentchaos.ttft_ms": ev.ttft_ms,
                    "agentchaos.fidelity": ev.fidelity,
                    "gen_ai.usage.input_tokens": usage.get("input_tokens"),
                    "gen_ai.usage.output_tokens": usage.get("output_tokens"),
                    GEN_AI_COST_USD_ATTR: usage.get("cost_usd"),
                }
            )
        )
        if ev.error is not None:
            turn.spec.status = "error"
            turn.spec.status_description = ev.error
        self._close_turn(_ns(ev.timestamp))

    def on_model_call(self, ev: ModelCall) -> None:
        parent = self._current_parent()
        end = _ns(ev.timestamp)
        self._add_leaf(
            SpanSpec(
                spec_id=self._next_id(),
                parent_id=parent.spec_id,
                name=f"chat {ev.model}",
                kind="client",
                start_time_unix_nano=_leaf_start(end, ev.latency_ms),
                end_time_unix_nano=end,
                attributes=_attrs(
                    {
                        "gen_ai.operation.name": "chat",
                        "gen_ai.system": infer_gen_ai_system(ev.model),
                        "gen_ai.request.model": ev.model,
                        "gen_ai.response.model": ev.model,
                        "gen_ai.usage.input_tokens": ev.input_tokens,
                        "gen_ai.usage.output_tokens": ev.output_tokens,
                        "gen_ai.response.finish_reasons": (
                            [ev.stop_reason] if ev.stop_reason is not None else None
                        ),
                        GEN_AI_COST_USD_ATTR: ev.cost_usd,
                        "agentchaos.ttft_ms": ev.ttft_ms,
                        "agentchaos.turn_index": ev.turn_index,
                        "agentchaos.call_index": ev.call_index,
                        "agentchaos.call_name": ev.name,
                    }
                ),
            )
        )

    def on_tool_call(self, ev: ToolCall) -> None:
        parent = self._current_parent()
        end = _ns(ev.timestamp)
        is_error = ev.error is not None or ev.result_summary in ("error", "malformed")
        self._add_leaf(
            SpanSpec(
                spec_id=self._next_id(),
                parent_id=parent.spec_id,
                name=f"execute_tool {ev.name}",
                kind="internal",
                start_time_unix_nano=_leaf_start(end, ev.latency_ms),
                end_time_unix_nano=end,
                attributes=_attrs(
                    {
                        "gen_ai.operation.name": "execute_tool",
                        "gen_ai.tool.name": ev.name,
                        "agentchaos.args_hash": ev.args_hash,
                        "agentchaos.retries": ev.retries,
                        "agentchaos.result_summary": ev.result_summary,
                        "agentchaos.result_size_bytes": ev.result_size_bytes,
                        "agentchaos.turn_index": ev.turn_index,
                        "agentchaos.call_index": ev.call_index,
                    }
                ),
                status="error" if is_error else "unset",
                status_description=(ev.error or ev.result_summary) if is_error else None,
            )
        )

    def on_chaos_injected(self, ev: ChaosInjected) -> None:
        parent = self._current_parent()
        t = _ns(ev.timestamp)
        self._add_leaf(
            SpanSpec(
                spec_id=self._next_id(),
                parent_id=parent.spec_id,
                name=f"chaos_injected {ev.tool_name}",
                kind="internal",
                start_time_unix_nano=t,
                end_time_unix_nano=t,
                attributes=_attrs(
                    {
                        "gen_ai.tool.name": ev.tool_name,
                        "agentchaos.chaos.target": ev.target,
                        "agentchaos.chaos.policy": ev.policy,
                        "agentchaos.chaos.injection_type": ev.injection_type,
                        "agentchaos.chaos.value": ev.value,
                        "agentchaos.args_hash": ev.args_hash,
                    }
                ),
            )
        )

    def on_retry(self, ev: Retry) -> None:
        t = _ns(ev.timestamp)
        self._current_parent().events.append(
            SpanEventSpec(
                name="retry",
                time_unix_nano=t,
                attributes=_attrs(
                    {
                        "agentchaos.attempt": ev.attempt,
                        "agentchaos.reason": ev.reason,
                        "agentchaos.backoff_ms": ev.backoff_ms,
                        "agentchaos.logical_call_index": ev.logical_call_index,
                        "agentchaos.turn_index": ev.turn_index,
                    }
                ),
            )
        )
        self._track_end(t)

    def on_tool_response(self, ev: ToolResponse) -> None:
        t = _ns(ev.timestamp)
        self._current_parent().events.append(
            SpanEventSpec(
                name="tool_response",
                time_unix_nano=t,
                attributes=_attrs(
                    {
                        "gen_ai.tool.name": ev.tool_name,
                        "agentchaos.status": ev.status,
                        "agentchaos.size_bytes": ev.size_bytes,
                        "agentchaos.chaos_injected": ev.chaos_injected,
                        "agentchaos.args_hash": ev.args_hash,
                    }
                ),
            )
        )
        self._track_end(t)

    def on_session_end(self, ev: SessionEnd) -> None:
        root = self._require_root()
        t = _ns(ev.timestamp)
        root.events.append(SpanEventSpec(name="session_end", time_unix_nano=t))
        root.attributes.update(
            _attrs(
                {
                    GEN_AI_TOTAL_COST_USD_ATTR: ev.total_cost_usd,
                    "agentchaos.total_latency_ms": ev.total_latency_ms,
                    "agentchaos.turns": ev.turns,
                    "agentchaos.tool_calls": ev.tool_calls,
                    "agentchaos.model_calls": ev.model_calls,
                    "agentchaos.retries": ev.retries,
                    "agentchaos.session_outcome": ev.outcome,
                }
            )
        )
        self.max_end_ns = max(self.max_end_ns, t)

    def on_run_end(self, ev: RunEnd) -> None:
        root = self._require_root()
        root.end_time_unix_nano = max(_ns(ev.finished_at), root.start_time_unix_nano)
        root.attributes.update(
            {"agentchaos.outcome": ev.outcome, "agentchaos.exit_code": ev.exit_code}
        )
        if ev.outcome == "fail":
            root.status = "error"
            root.status_description = f"run failed (exit {ev.exit_code})"
        self.root_closed = True

    def finish(self) -> list[SpanSpec]:
        root = self._require_root()
        self._close_turn(None)
        if not self.root_closed:
            root.end_time_unix_nano = max(
                self.max_end_ns or root.start_time_unix_nano, root.start_time_unix_nano
            )
        return self.specs


def build_spans(events: Iterable[TraceEvent]) -> list[SpanSpec]:
    """Map trace events (in seq order) to SpanSpecs, parents before children.

    Single pass; raises SpanBuildError if the trace contains no run_meta event.
    """
    builder = _Builder()
    for ev in events:
        if isinstance(ev, RunMeta):
            builder.on_run_meta(ev)
        elif isinstance(ev, SessionStart):
            builder.on_session_start(ev)
        elif isinstance(ev, UserTurn):
            builder.on_user_turn(ev)
        elif isinstance(ev, AgentTurn):
            builder.on_agent_turn(ev)
        elif isinstance(ev, ModelCall):
            builder.on_model_call(ev)
        elif isinstance(ev, ToolCall):
            builder.on_tool_call(ev)
        elif isinstance(ev, ChaosInjected):
            builder.on_chaos_injected(ev)
        elif isinstance(ev, Retry):
            builder.on_retry(ev)
        elif isinstance(ev, ToolResponse):
            builder.on_tool_response(ev)
        elif isinstance(ev, SessionEnd):
            builder.on_session_end(ev)
        elif isinstance(ev, RunEnd):
            builder.on_run_end(ev)
    return builder.finish()
