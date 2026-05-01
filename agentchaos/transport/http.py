"""HTTP transport with three-tier fidelity detection.

Sends ``{"session_id", "message"}`` POST requests to the agent endpoint and
parses the response into a normalised :class:`AgentTurnResult`. The transport
never raises on agent-side errors — it records them on the result.
"""
from __future__ import annotations

import json as _json
import time
from typing import Any

import httpx

from agentchaos.scenario.schema import AgentTarget
from agentchaos.transport.base import AgentTransport, AgentTurnResult, FidelityTier


class HTTPTransport(AgentTransport):
    def __init__(
        self,
        target: AgentTarget,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._target = target
        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            self._client = httpx.AsyncClient(
                timeout=target.timeout_s,
                headers=dict(target.headers),
            )
            self._owns_client = True

    async def send(self, session_id: str, message: str) -> AgentTurnResult:
        endpoint = str(self._target.endpoint)
        body_out = {"session_id": session_id, "message": message}
        t0 = time.perf_counter()
        try:
            resp = await self._client.post(endpoint, json=body_out)
        except httpx.TimeoutException:
            return AgentTurnResult(
                text="",
                latency_ms=_elapsed_ms(t0),
                fidelity=FidelityTier.MESSAGE_ONLY,
                error="timeout",
            )
        except httpx.RequestError as exc:
            return AgentTurnResult(
                text="",
                latency_ms=_elapsed_ms(t0),
                fidelity=FidelityTier.MESSAGE_ONLY,
                error=f"request_error: {exc!r}",
            )
        latency_ms = _elapsed_ms(t0)
        if resp.status_code >= 400:
            return AgentTurnResult(
                text="",
                latency_ms=latency_ms,
                fidelity=FidelityTier.MESSAGE_ONLY,
                error=f"http_{resp.status_code}",
                status_code=resp.status_code,
            )
        try:
            body = resp.json()
        except _json.JSONDecodeError:
            return AgentTurnResult(
                text=resp.text[:200],
                latency_ms=latency_ms,
                fidelity=FidelityTier.MESSAGE_ONLY,
                error="non_json_response",
                status_code=resp.status_code,
            )
        if not isinstance(body, dict):
            return AgentTurnResult(
                text="",
                latency_ms=latency_ms,
                fidelity=FidelityTier.MESSAGE_ONLY,
                error="response_not_object",
                status_code=resp.status_code,
            )
        return _parse_body(body, latency_ms, resp.status_code)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def _elapsed_ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def _parse_body(body: dict[str, Any], latency_ms: int, status_code: int) -> AgentTurnResult:
    text = body.get("message", "") or ""
    agent = body.get("agent") if isinstance(body.get("agent"), dict) else None
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else None
    raw_events = body.get("events")
    raw_tool_calls = body.get("tool_calls")

    events: list[dict[str, Any]]
    if isinstance(raw_events, list):
        fidelity = FidelityTier.FULL
        events = [e for e in raw_events if isinstance(e, dict)]
    elif isinstance(raw_tool_calls, list) or usage is not None:
        fidelity = FidelityTier.AGGREGATE
        events = []
        if isinstance(raw_tool_calls, list):
            for tc in raw_tool_calls:
                if isinstance(tc, dict):
                    events.append({"type": "tool_call", **tc})
    else:
        fidelity = FidelityTier.MESSAGE_ONLY
        events = []

    return AgentTurnResult(
        text=text,
        events=events,
        usage=usage,
        agent=agent,
        fidelity=fidelity,
        latency_ms=latency_ms,
        status_code=status_code,
    )
