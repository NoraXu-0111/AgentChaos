"""End-to-end `agentchaos export-otel` tests against an in-process OTLP/HTTP sink."""
from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from fastapi import FastAPI, Request, Response
from typer.testing import CliRunner

pytest.importorskip("opentelemetry")

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)

from agentchaos.cli import app

pytestmark = pytest.mark.integration


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_ready(url: str, timeout_s: float = 5.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            httpx.get(url, timeout=0.5)
            return
        except Exception:
            time.sleep(0.05)
    raise RuntimeError(f"server at {url} did not become ready")


def _make_sink(captured: list[dict[str, Any]]) -> FastAPI:
    app_ = FastAPI()

    @app_.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app_.post("/v1/traces")
    async def traces(request: Request) -> Response:
        captured.append(
            {"body": await request.body(), "headers": dict(request.headers)}
        )
        return Response(content=b"", media_type="application/x-protobuf")

    return app_


@pytest.fixture
def otlp_sink() -> Iterator[tuple[str, list[dict[str, Any]]]]:
    captured: list[dict[str, Any]] = []
    port = _free_port()
    config = uvicorn.Config(
        _make_sink(captured), host="127.0.0.1", port=port, log_level="error"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        _wait_ready(f"http://127.0.0.1:{port}/health")
        yield f"http://127.0.0.1:{port}/v1/traces", captured
    finally:
        server.should_exit = True
        thread.join(timeout=3)


def _decode(body: bytes) -> ExportTraceServiceRequest:
    req = ExportTraceServiceRequest()
    req.ParseFromString(body)
    return req


def _resource_attr(resource_spans, key: str) -> Any:
    for kv in resource_spans.resource.attributes:
        if kv.key == key:
            return kv.value.string_value
    return None


def _span_attrs(span) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for kv in span.attributes:
        value = kv.value
        which = value.WhichOneof("value")
        out[kv.key] = getattr(value, which) if which else None
    return out


def test_export_otel_end_to_end_otlp_http(
    otel_trace_file: Path, otlp_sink: tuple[str, list[dict[str, Any]]]
) -> None:
    endpoint, captured = otlp_sink
    runner = CliRunner()
    result = runner.invoke(
        app, ["export-otel", str(otel_trace_file), "--endpoint", endpoint]
    )
    assert result.exit_code == 0, result.output
    assert "Exported 7 span(s)" in result.stdout

    assert len(captured) == 1
    request = captured[0]
    assert request["headers"]["content-type"] == "application/x-protobuf"

    decoded = _decode(request["body"])
    assert len(decoded.resource_spans) == 1
    resource_spans = decoded.resource_spans[0]
    assert _resource_attr(resource_spans, "service.name") == "agentchaos"
    assert _resource_attr(resource_spans, "service.version") == "0.1.0"

    spans = [s for scope in resource_spans.scope_spans for s in scope.spans]
    assert len(spans) == 7

    by_name = {s.name: s for s in spans}
    model = by_name["chat gpt-4o-mini"]
    attrs = _span_attrs(model)
    assert attrs["gen_ai.request.model"] == "gpt-4o-mini"
    assert attrs["gen_ai.usage.input_tokens"] == 100
    assert attrs["gen_ai.usage.output_tokens"] == 20
    assert attrs["agentchaos.cost_usd"] == 0.001

    roots = [s for s in spans if not s.parent_span_id]
    assert len(roots) == 1
    root = roots[0]
    assert root.name == "agentchaos.run refund-agent"
    turns = [s for s in spans if s.name.startswith("turn ")]
    assert len(turns) == 2
    assert all(t.parent_span_id == root.span_id for t in turns)
    turn_ids = {bytes(t.span_id) for t in turns}
    leaves = [s for s in spans if s is not root and s not in turns]
    assert len(leaves) == 4
    assert all(bytes(leaf.parent_span_id) in turn_ids for leaf in leaves)


def test_export_otel_collector_unreachable_exit_4(otel_trace_file: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "export-otel", str(otel_trace_file),
            "--endpoint", "http://127.0.0.1:9/v1/traces",
            "--timeout-s", "1",
        ],
    )
    assert result.exit_code == 4, result.output


def test_export_otel_custom_service_name_and_header(
    otel_trace_file: Path, otlp_sink: tuple[str, list[dict[str, Any]]]
) -> None:
    endpoint, captured = otlp_sink
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "export-otel", str(otel_trace_file),
            "--endpoint", endpoint,
            "--service-name", "myagent",
            "--header", "x-api-key=abc",
        ],
    )
    assert result.exit_code == 0, result.output
    assert len(captured) == 1
    request = captured[0]
    assert request["headers"]["x-api-key"] == "abc"
    decoded = _decode(request["body"])
    assert _resource_attr(decoded.resource_spans[0], "service.name") == "myagent"
