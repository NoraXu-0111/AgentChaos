"""Unit tests for the pure trace -> SpanSpec mapping (no otel install required)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from agentchaos.otel.spans import (
    SpanBuildError,
    SpanEventSpec,
    SpanSpec,
    _ns,
    build_spans,
    infer_gen_ai_system,
)
from agentchaos.trace.schema import (
    AgentTurn,
    ModelCall,
    RunMeta,
    ToolCall,
    TraceEvent,
    UserTurn,
)

_BASE = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)


def _at(seconds: float) -> datetime:
    return _BASE + timedelta(seconds=seconds)


def _meta(seq: int = 0) -> RunMeta:
    return RunMeta(
        run_id="r1", seq=seq, timestamp=_at(0),
        agentchaos_version="0.1.0", scenario_path="s.yaml",
        scenario_hash="sha256:x", scenario_name="sc", started_at=_at(0),
    )


def _by_name(specs: list[SpanSpec], name: str) -> SpanSpec:
    return next(s for s in specs if s.name == name)


# ---------------------------------------------------------------------------
# infer_gen_ai_system
# ---------------------------------------------------------------------------


def test_infer_system_openai() -> None:
    assert infer_gen_ai_system("gpt-4o-mini") == "openai"


def test_infer_system_case_insensitive() -> None:
    assert infer_gen_ai_system("Claude-3-5-Sonnet") == "anthropic"


def test_infer_system_unknown_fallback() -> None:
    assert infer_gen_ai_system("my-custom-model") == "unknown"


# ---------------------------------------------------------------------------
# SpanSpec / SpanEventSpec models
# ---------------------------------------------------------------------------


def test_span_spec_roundtrip_json() -> None:
    spec = SpanSpec(
        spec_id=1, parent_id=0, name="chat gpt-4o-mini", kind="client",
        start_time_unix_nano=100, end_time_unix_nano=200,
        attributes={"gen_ai.request.model": "gpt-4o-mini", "agentchaos.cost_usd": 0.001},
        status="error", status_description="boom",
        events=[SpanEventSpec(name="retry", time_unix_nano=150, attributes={"a": 1})],
    )
    assert SpanSpec.model_validate_json(spec.model_dump_json()) == spec


def test_span_spec_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        SpanSpec(
            spec_id=0, name="x", start_time_unix_nano=0, end_time_unix_nano=0,
            bogus="nope",  # type: ignore[call-arg]
        )


def test_span_event_spec_negative_time_rejected() -> None:
    with pytest.raises(ValidationError):
        SpanEventSpec(name="retry", time_unix_nano=-1)


# ---------------------------------------------------------------------------
# build_spans
# ---------------------------------------------------------------------------


def test_build_spans_full_trace_topology(otel_trace_events: list[TraceEvent]) -> None:
    specs = build_spans(otel_trace_events)
    root = specs[0]
    assert root.name == "agentchaos.run refund-agent"
    assert root.parent_id is None

    turns = [s for s in specs if s.name.startswith("turn ")]
    assert len(turns) == 2
    leaves = [s for s in specs if s is not root and s not in turns]
    # 1 model_call + 2 tool_calls + 1 chaos_injected
    assert len(leaves) == 4
    assert len(specs) == 7

    ids = {s.spec_id for s in specs}
    assert all(s.parent_id in ids for s in specs if s.parent_id is not None)
    turn_ids = {s.spec_id for s in turns}
    assert all(leaf.parent_id in turn_ids for leaf in leaves)
    assert all(t.parent_id == root.spec_id for t in turns)
    # Parents come before children in the output order.
    pos = {s.spec_id: i for i, s in enumerate(specs)}
    assert all(pos[s.parent_id] < pos[s.spec_id] for s in specs if s.parent_id is not None)


def test_build_spans_model_call_semconv_attrs(otel_trace_events: list[TraceEvent]) -> None:
    specs = build_spans(otel_trace_events)
    model = _by_name(specs, "chat gpt-4o-mini")
    assert model.kind == "client"
    a = model.attributes
    assert a["gen_ai.operation.name"] == "chat"
    assert a["gen_ai.system"] == "openai"
    assert a["gen_ai.request.model"] == "gpt-4o-mini"
    assert a["gen_ai.response.model"] == "gpt-4o-mini"
    assert a["gen_ai.usage.input_tokens"] == 100
    assert a["gen_ai.usage.output_tokens"] == 20
    assert a["gen_ai.response.finish_reasons"] == ["stop"]
    assert a["agentchaos.cost_usd"] == 0.001


def test_build_spans_latency_maps_to_start_time(otel_trace_events: list[TraceEvent]) -> None:
    specs = build_spans(otel_trace_events)
    model = _by_name(specs, "chat gpt-4o-mini")
    model_event = next(e for e in otel_trace_events if isinstance(e, ModelCall))
    assert model.end_time_unix_nano == _ns(model_event.timestamp)
    assert model.end_time_unix_nano - model.start_time_unix_nano == 200 * 1_000_000


def test_build_spans_missing_latency_zero_duration(otel_trace_events: list[TraceEvent]) -> None:
    specs = build_spans(otel_trace_events)
    tool = _by_name(specs, "execute_tool get_order")
    assert tool.start_time_unix_nano == tool.end_time_unix_nano


def test_build_spans_no_run_meta_raises() -> None:
    events: list[TraceEvent] = [
        UserTurn(run_id="r1", seq=0, timestamp=_at(1), turn_index=0, text="hi"),
    ]
    with pytest.raises(SpanBuildError, match="run_meta"):
        build_spans(events)


def test_build_spans_empty_iterable_raises() -> None:
    with pytest.raises(SpanBuildError, match="run_meta"):
        build_spans([])


def test_build_spans_truncated_trace_root_end(otel_trace_events: list[TraceEvent]) -> None:
    # Cut right after the first ToolCall: no agent_turn/session_end/run_end.
    truncated = otel_trace_events[:5]
    assert isinstance(truncated[-1], ToolCall)
    specs = build_spans(truncated)
    root = specs[0]
    turn = _by_name(specs, "turn 0")
    tool = _by_name(specs, "execute_tool get_order")
    max_child_end = max(tool.end_time_unix_nano, _by_name(specs, "chat gpt-4o-mini").end_time_unix_nano)
    assert turn.end_time_unix_nano == max_child_end
    assert root.end_time_unix_nano == max_child_end
    assert "agentchaos.outcome" not in root.attributes


def test_build_spans_tool_error_status(otel_trace_events: list[TraceEvent]) -> None:
    specs = build_spans(otel_trace_events)
    tool = _by_name(specs, "execute_tool create_return_label")
    assert tool.status == "error"
    assert tool.status_description == "label service boom"


def test_build_spans_run_fail_marks_root_error(otel_trace_events: list[TraceEvent]) -> None:
    events = list(otel_trace_events)
    run_end = events[-1].model_copy(update={"outcome": "fail", "exit_code": 2})
    events[-1] = run_end
    specs = build_spans(events)
    root = specs[0]
    assert root.status == "error"
    assert root.status_description == "run failed (exit 2)"
    assert root.attributes["agentchaos.exit_code"] == 2
    assert root.attributes["agentchaos.outcome"] == "fail"


def test_build_spans_chaos_span_attrs(otel_trace_events: list[TraceEvent]) -> None:
    specs = build_spans(otel_trace_events)
    chaos = _by_name(specs, "chaos_injected get_order")
    assert chaos.start_time_unix_nano == chaos.end_time_unix_nano
    a = chaos.attributes
    assert a["gen_ai.tool.name"] == "get_order"
    assert a["agentchaos.chaos.target"] == "get_order"
    assert a["agentchaos.chaos.policy"] == "fail-503"
    assert a["agentchaos.chaos.injection_type"] == "status_code"
    assert a["agentchaos.chaos.value"] == 503
    assert a["agentchaos.args_hash"] == "hash-get-order"


def test_build_spans_fidelity_message_only_omits_usage() -> None:
    events: list[TraceEvent] = [
        _meta(),
        UserTurn(run_id="r1", seq=1, timestamp=_at(1), turn_index=0, text="hi"),
        AgentTurn(
            run_id="r1", seq=2, timestamp=_at(2), turn_index=0, text="ok",
            latency_ms=1000, usage=None, fidelity="message_only",
        ),
    ]
    specs = build_spans(events)
    turn = _by_name(specs, "turn 0")
    assert turn.attributes["agentchaos.fidelity"] == "message_only"
    assert not any(k.startswith("gen_ai.usage.") for k in turn.attributes)


def test_build_spans_unclosed_turn_closed_by_next_user_turn() -> None:
    events: list[TraceEvent] = [
        _meta(),
        UserTurn(run_id="r1", seq=1, timestamp=_at(1), turn_index=0, text="hi"),
        UserTurn(run_id="r1", seq=2, timestamp=_at(5), turn_index=1, text="hello?"),
    ]
    specs = build_spans(events)
    first = _by_name(specs, "turn 0")
    second = _by_name(specs, "turn 1")
    assert first.end_time_unix_nano == second.start_time_unix_nano == _ns(_at(5))


def test_build_spans_retry_and_tool_response_become_span_events(
    otel_trace_events: list[TraceEvent],
) -> None:
    specs = build_spans(otel_trace_events)
    turn = _by_name(specs, "turn 0")
    retry = next(e for e in turn.events if e.name == "retry")
    assert retry.attributes["agentchaos.attempt"] == 1
    assert retry.attributes["agentchaos.reason"] == "503"
    assert retry.attributes["agentchaos.backoff_ms"] == 100
    assert retry.attributes["agentchaos.logical_call_index"] == 0
    assert retry.attributes["agentchaos.turn_index"] == 0
    resp = next(e for e in turn.events if e.name == "tool_response")
    assert resp.attributes["gen_ai.tool.name"] == "get_order"
    assert resp.attributes["agentchaos.status"] == 200
    assert resp.attributes["agentchaos.size_bytes"] == 128
    assert resp.attributes["agentchaos.chaos_injected"] is True
    assert resp.attributes["agentchaos.args_hash"] == "hash-get-order"


def test_build_spans_clock_skew_clamps_start() -> None:
    # Negative latency simulates clock skew: computed start would exceed end.
    events: list[TraceEvent] = [
        _meta(),
        UserTurn(run_id="r1", seq=1, timestamp=_at(1), turn_index=0, text="hi"),
        ModelCall(
            run_id="r1", seq=2, timestamp=_at(2), turn_index=0, call_index=0,
            model="gpt-4o-mini", latency_ms=-500,
        ),
    ]
    specs = build_spans(events)
    model = _by_name(specs, "chat gpt-4o-mini")
    assert model.start_time_unix_nano == model.end_time_unix_nano
    assert all(s.start_time_unix_nano <= s.end_time_unix_nano for s in specs)


def test_build_spans_none_attrs_omitted() -> None:
    events: list[TraceEvent] = [
        _meta(),
        UserTurn(run_id="r1", seq=1, timestamp=_at(1), turn_index=0, text="hi"),
        ModelCall(
            run_id="r1", seq=2, timestamp=_at(2), turn_index=0, call_index=0,
            model="gpt-4o-mini", cost_usd=None, input_tokens=None,
        ),
    ]
    specs = build_spans(events)
    model = _by_name(specs, "chat gpt-4o-mini")
    assert "agentchaos.cost_usd" not in model.attributes
    assert "gen_ai.usage.input_tokens" not in model.attributes
    assert all(v is not None for v in model.attributes.values())
