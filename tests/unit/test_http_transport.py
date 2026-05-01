"""Tests for HTTPTransport fidelity detection and error handling."""
from __future__ import annotations

import httpx
import pytest

from agentchaos.scenario.schema import AgentTarget
from agentchaos.transport import FidelityTier, HTTPTransport


@pytest.fixture
def target() -> AgentTarget:
    return AgentTarget(endpoint="http://test.local/chat")  # type: ignore[arg-type]


def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5)


async def test_full_fidelity_detection(target: AgentTarget) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "session_id": "s-1",
                "message": "hi",
                "agent": {"name": "a", "version": "1", "model": "gpt-4o-mini"},
                "events": [
                    {
                        "type": "model_call",
                        "model": "gpt-4o-mini",
                        "input_tokens": 100,
                        "output_tokens": 20,
                        "cost_usd": 0.0001,
                        "latency_ms": 200,
                    },
                    {
                        "type": "tool_call",
                        "name": "get_order",
                        "args": {"id": "1"},
                        "latency_ms": 50,
                        "result_summary": "ok",
                    },
                ],
                "usage": {"input_tokens": 100, "output_tokens": 20, "cost_usd": 0.0001},
            },
        )

    transport = HTTPTransport(target, client=_mock_client(handler))
    res = await transport.send("s-1", "hello")
    await transport.aclose()
    assert res.fidelity is FidelityTier.FULL
    assert res.text == "hi"
    assert len(res.events) == 2
    assert res.usage is not None
    assert res.agent is not None
    assert res.error is None
    assert res.status_code == 200


async def test_aggregate_fidelity_detection(target: AgentTarget) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "session_id": "s-1",
                "message": "hi",
                "tool_calls": [
                    {"name": "get_order", "args": {"id": "1"}, "latency_ms": 50},
                ],
                "usage": {"input_tokens": 100, "output_tokens": 20, "cost_usd": 0.0001},
            },
        )

    transport = HTTPTransport(target, client=_mock_client(handler))
    res = await transport.send("s-1", "hello")
    await transport.aclose()
    assert res.fidelity is FidelityTier.AGGREGATE
    assert len(res.events) == 1
    assert res.events[0]["type"] == "tool_call"


async def test_message_only_fidelity_detection(target: AgentTarget) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": "ok"})

    transport = HTTPTransport(target, client=_mock_client(handler))
    res = await transport.send("s-1", "hello")
    await transport.aclose()
    assert res.fidelity is FidelityTier.MESSAGE_ONLY
    assert res.text == "ok"
    assert res.usage is None


async def test_http_error_does_not_raise(target: AgentTarget) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    transport = HTTPTransport(target, client=_mock_client(handler))
    res = await transport.send("s-1", "hello")
    await transport.aclose()
    assert res.error == "http_500"
    assert res.fidelity is FidelityTier.MESSAGE_ONLY
    assert res.status_code == 500


async def test_timeout_does_not_raise(target: AgentTarget) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    transport = HTTPTransport(target, client=_mock_client(handler))
    res = await transport.send("s-1", "hello")
    await transport.aclose()
    assert res.error == "timeout"


async def test_connection_error_does_not_raise(target: AgentTarget) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    transport = HTTPTransport(target, client=_mock_client(handler))
    res = await transport.send("s-1", "hello")
    await transport.aclose()
    assert res.error is not None
    assert "request_error" in res.error


async def test_non_json_response_does_not_raise(target: AgentTarget) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json", headers={"content-type": "text/plain"})

    transport = HTTPTransport(target, client=_mock_client(handler))
    res = await transport.send("s-1", "hello")
    await transport.aclose()
    assert res.error == "non_json_response"
    assert res.fidelity is FidelityTier.MESSAGE_ONLY


async def test_response_object_required(target: AgentTarget) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["not", "an", "object"])

    transport = HTTPTransport(target, client=_mock_client(handler))
    res = await transport.send("s-1", "hello")
    await transport.aclose()
    assert res.error == "response_not_object"


async def test_request_includes_session_and_message(target: AgentTarget) -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = req.read().decode()
        return httpx.Response(200, json={"message": "ok"})

    transport = HTTPTransport(target, client=_mock_client(handler))
    await transport.send("session-abc", "user message")
    await transport.aclose()
    assert "session-abc" in captured["body"]
    assert "user message" in captured["body"]


async def test_aclose_idempotent_when_external_client_passed(target: AgentTarget) -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"message": "hi"})))
    transport = HTTPTransport(target, client=client)
    await transport.send("s-1", "x")
    # external client: aclose should not close the user's client
    await transport.aclose()
    # We can still use the external client
    assert not client.is_closed
    await client.aclose()
