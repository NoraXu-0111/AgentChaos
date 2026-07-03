"""OpenTelemetry export for AgentChaos traces.

Only the pure mapping layer is re-exported here; ``agentchaos.otel.emit`` (the
sole module importing ``opentelemetry``) must be imported explicitly so this
package stays usable without the [otel] extra.
"""
from __future__ import annotations

from agentchaos.otel.spans import (
    SpanBuildError,
    SpanEventSpec,
    SpanSpec,
    build_spans,
    infer_gen_ai_system,
)

__all__ = [
    "SpanBuildError",
    "SpanEventSpec",
    "SpanSpec",
    "build_spans",
    "infer_gen_ai_system",
]
