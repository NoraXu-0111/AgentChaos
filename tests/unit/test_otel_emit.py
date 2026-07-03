"""Unit tests for the SpanSpec -> OTel SDK emitter (requires the [otel] extra)."""
from __future__ import annotations

import pytest

pytest.importorskip("opentelemetry")

from collections.abc import Sequence

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace.status import StatusCode

from agentchaos.otel import emit as emit_module
from agentchaos.otel.emit import OtelExportError, emit_spans, make_otlp_http_exporter
from agentchaos.otel.spans import build_spans
from agentchaos.trace.schema import TraceEvent

# ---------------------------------------------------------------------------
# emit_spans
# ---------------------------------------------------------------------------


def test_emit_spans_exports_all_specs_in_memory(otel_trace_events: list[TraceEvent]) -> None:
    specs = build_spans(otel_trace_events)
    exporter = InMemorySpanExporter()
    count = emit_spans(specs, exporter)
    exported = exporter.get_finished_spans()
    assert count == len(specs) == len(exported)
    assert {s.name for s in exported} == {s.name for s in specs}

    by_name = {s.name: s for s in exported}
    root = by_name["agentchaos.run refund-agent"]
    assert root.parent is None
    span_ids = {spec.spec_id: by_name[spec.name].context.span_id for spec in specs}
    for spec in specs:
        exported_span = by_name[spec.name]
        if spec.parent_id is None:
            assert exported_span.parent is None
        else:
            assert exported_span.parent is not None
            assert exported_span.parent.span_id == span_ids[spec.parent_id]
    assert len({s.context.trace_id for s in exported}) == 1


def test_emit_spans_preserves_times_attrs_status(otel_trace_events: list[TraceEvent]) -> None:
    specs = build_spans(otel_trace_events)
    exporter = InMemorySpanExporter()
    emit_spans(specs, exporter)
    by_name = {s.name: s for s in exporter.get_finished_spans()}
    for spec in specs:
        exported = by_name[spec.name]
        assert exported.start_time == spec.start_time_unix_nano
        assert exported.end_time == spec.end_time_unix_nano

    model = by_name["chat gpt-4o-mini"]
    assert model.attributes is not None
    assert model.attributes["gen_ai.request.model"] == "gpt-4o-mini"
    assert model.attributes["gen_ai.usage.input_tokens"] == 100
    assert model.attributes["gen_ai.usage.output_tokens"] == 20
    assert model.attributes["agentchaos.cost_usd"] == 0.001

    failing_tool = by_name["execute_tool create_return_label"]
    assert failing_tool.status.status_code is StatusCode.ERROR
    assert failing_tool.status.description == "label service boom"


def test_emit_spans_empty_returns_zero() -> None:
    exporter = InMemorySpanExporter()
    assert emit_spans([], exporter) == 0
    assert exporter.get_finished_spans() == ()


def test_emit_spans_failure_raises_export_error(otel_trace_events: list[TraceEvent]) -> None:
    class _FailingExporter(SpanExporter):
        def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
            return SpanExportResult.FAILURE

        def shutdown(self) -> None:
            pass

    specs = build_spans(otel_trace_events)
    with pytest.raises(OtelExportError):
        emit_spans(specs, _FailingExporter())


def test_emit_spans_sets_resource(otel_trace_events: list[TraceEvent]) -> None:
    specs = build_spans(otel_trace_events)
    exporter = InMemorySpanExporter()
    emit_spans(specs, exporter, service_name="myagent", service_version="0.1.0")
    for span in exporter.get_finished_spans():
        assert span.resource.attributes["service.name"] == "myagent"
        assert span.resource.attributes["service.version"] == "0.1.0"


# ---------------------------------------------------------------------------
# make_otlp_http_exporter
# ---------------------------------------------------------------------------


def test_make_exporter_returns_otlp_http_type() -> None:
    exporter = make_otlp_http_exporter("http://localhost:4318/v1/traces")
    assert isinstance(exporter, OTLPSpanExporter)


def test_make_exporter_passes_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _FakeExporter:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(emit_module, "OTLPSpanExporter", _FakeExporter)
    make_otlp_http_exporter(
        "http://localhost:4318/v1/traces", headers={"x-api-key": "abc"}, timeout_s=3.0
    )
    assert captured["endpoint"] == "http://localhost:4318/v1/traces"
    assert captured["headers"] == {"x-api-key": "abc"}
    assert captured["timeout"] == 3.0


def test_make_exporter_default_timeout() -> None:
    default = make_otlp_http_exporter("http://localhost:4318/v1/traces")
    assert isinstance(default, OTLPSpanExporter)
    custom = make_otlp_http_exporter("http://localhost:4318/v1/traces", timeout_s=2.5)
    assert isinstance(custom, OTLPSpanExporter)
