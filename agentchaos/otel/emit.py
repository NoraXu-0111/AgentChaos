"""SpanSpec -> OpenTelemetry SDK spans -> exporter. Requires the [otel] extra.

Importing this module without opentelemetry installed raises ModuleNotFoundError;
the CLI catches that and prints an install hint.
"""
from __future__ import annotations

from collections.abc import Sequence

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.trace import NonRecordingSpan, SpanKind, set_span_in_context
from opentelemetry.trace.span import SpanContext
from opentelemetry.trace.status import Status, StatusCode

from agentchaos.otel.spans import SpanSpec


class OtelExportError(Exception):
    """Raised when the exporter reports a failed export (e.g. collector unreachable)."""


class _CapturingExporter(SpanExporter):
    """Accumulates finished spans so the real exporter receives one single batch."""

    def __init__(self) -> None:
        self.spans: list[ReadableSpan] = []

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:  # pragma: no cover - nothing to release
        pass


def make_otlp_http_exporter(
    endpoint: str,
    headers: dict[str, str] | None = None,
    timeout_s: float = 10.0,
) -> SpanExporter:
    """Create an OTLP HTTP/protobuf span exporter targeting a /v1/traces endpoint."""
    return OTLPSpanExporter(endpoint=endpoint, headers=headers, timeout=timeout_s)


def emit_spans(
    specs: Sequence[SpanSpec],
    exporter: SpanExporter,
    *,
    service_name: str = "agentchaos",
    service_version: str | None = None,
) -> int:
    """Replay SpanSpecs as real SDK spans through exporter; return the span count.

    Uses explicit start/end times and a per-call TracerProvider + SimpleSpanProcessor;
    raises OtelExportError if the export reports FAILURE.
    """
    if not specs:
        return 0

    resource_attrs: dict[str, str] = {"service.name": service_name}
    if service_version is not None:
        resource_attrs["service.version"] = service_version

    capturing = _CapturingExporter()
    provider = TracerProvider(resource=Resource.create(resource_attrs))
    provider.add_span_processor(SimpleSpanProcessor(capturing))
    tracer = provider.get_tracer("agentchaos.otel")

    contexts: dict[int, SpanContext] = {}
    try:
        for spec in specs:
            parent_context = None
            if spec.parent_id is not None and spec.parent_id in contexts:
                parent_context = set_span_in_context(NonRecordingSpan(contexts[spec.parent_id]))
            span = tracer.start_span(
                spec.name,
                context=parent_context,
                kind=SpanKind.CLIENT if spec.kind == "client" else SpanKind.INTERNAL,
                attributes=spec.attributes,
                start_time=spec.start_time_unix_nano,
            )
            contexts[spec.spec_id] = span.get_span_context()
            for event in spec.events:
                span.add_event(
                    event.name, attributes=event.attributes, timestamp=event.time_unix_nano
                )
            if spec.status == "error":
                span.set_status(Status(StatusCode.ERROR, spec.status_description))
            span.end(end_time=spec.end_time_unix_nano)
    finally:
        provider.force_flush()
        provider.shutdown()

    try:
        result = exporter.export(capturing.spans)
    except Exception as exc:
        raise OtelExportError(f"OTLP export failed: {exc}") from exc
    finally:
        exporter.shutdown()
    if result is not SpanExportResult.SUCCESS:
        raise OtelExportError(
            "OTLP export failed (collector unreachable or rejected the batch)"
        )
    return len(capturing.spans)
