"""Tests for the chaos forward-proxy."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from agentchaos.chaos.policy import ChaosPolicy, ChaosTarget, ToolChaosPolicy
from agentchaos.chaos.proxy import ChaosProxy, tool_name_from_path
from agentchaos.seq import SeqCounter
from agentchaos.trace.reader import read_trace
from agentchaos.trace.recorder import TraceRecorder
from agentchaos.trace.schema import ChaosInjected, ToolResponse


def test_tool_name_from_path() -> None:
    assert tool_name_from_path("/tools/get_order") == "get_order"
    assert tool_name_from_path("/tools/get_order/") == "get_order"
    assert tool_name_from_path("/tools/get_order?x=1") == "get_order"
    assert tool_name_from_path("/") == ""
    assert tool_name_from_path("get_order") == "get_order"


def _make_proxy(
    out: Path,
    policy: ChaosPolicy,
    handler,
    *,
    seed: int = 42,
) -> tuple[ChaosProxy, dict]:
    state = {"upstream_calls": 0}

    def wrapped(req: httpx.Request) -> httpx.Response:
        state["upstream_calls"] += 1
        return handler(req)

    client = httpx.AsyncClient(transport=httpx.MockTransport(wrapped), timeout=5)
    proxy = ChaosProxy(
        upstream_base_url="http://upstream.local",
        policy=policy,
        seed=seed,
        recorder=TraceRecorder(out),
        seq=SeqCounter(),
        run_id="run-1",
        session_id="s-1",
        client=client,
    )
    return proxy, state


async def test_status_injection_short_circuits(tmp_path: Path) -> None:
    out = tmp_path / "t.jsonl"
    policy = ChaosPolicy(
        targets=[ChaosTarget(tool="get_order",
                             policy=ToolChaosPolicy(failure_rate=1.0, status_code=503))]
    )

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    proxy, state = _make_proxy(out, policy, handler)
    resp = await proxy.handle("POST", "/tools/get_order", {}, b'{"order_id":"1"}')
    await proxy.aclose()

    assert resp.status == 503
    assert state["upstream_calls"] == 0  # upstream NOT called
    assert proxy.injected_count == 1

    events = list(read_trace(out))
    chaos = [e for e in events if isinstance(e, ChaosInjected)]
    responses = [e for e in events if isinstance(e, ToolResponse)]
    assert len(chaos) == 1
    assert chaos[0].injection_type == "status_code"
    assert chaos[0].value == 503
    assert chaos[0].args_hash is not None
    assert len(responses) == 1
    assert responses[0].status == 503
    assert responses[0].chaos_injected is True


async def test_untargeted_tool_forwarded(tmp_path: Path) -> None:
    out = tmp_path / "t.jsonl"
    policy = ChaosPolicy(
        targets=[ChaosTarget(tool="get_order", policy=ToolChaosPolicy(failure_rate=1.0))]
    )

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"label": "abc"})

    proxy, state = _make_proxy(out, policy, handler)
    resp = await proxy.handle("POST", "/tools/create_return_label", {}, b'{"order_id":"1"}')
    await proxy.aclose()

    assert resp.status == 200
    assert state["upstream_calls"] == 1
    assert proxy.injected_count == 0
    events = list(read_trace(out))
    assert not any(isinstance(e, ChaosInjected) for e in events)
    responses = [e for e in events if isinstance(e, ToolResponse)]
    assert len(responses) == 1
    assert responses[0].chaos_injected is False
    assert responses[0].body == {"label": "abc"}


async def test_latency_sleeps_then_forwards(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "t.jsonl"
    policy = ChaosPolicy(
        targets=[ChaosTarget(tool="get_order", policy=ToolChaosPolicy(latency_ms=250))]
    )
    slept: list[float] = []

    async def fake_sleep(secs: float) -> None:
        slept.append(secs)

    monkeypatch.setattr("agentchaos.chaos.proxy.asyncio.sleep", fake_sleep)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    proxy, state = _make_proxy(out, policy, handler)
    resp = await proxy.handle("POST", "/tools/get_order", {}, b'{"order_id":"1"}')
    await proxy.aclose()

    assert slept == [0.25]
    assert resp.status == 200
    assert state["upstream_calls"] == 1  # forwarded after sleeping
    events = list(read_trace(out))
    chaos = [e for e in events if isinstance(e, ChaosInjected)]
    assert len(chaos) == 1
    assert chaos[0].injection_type == "latency"
    assert chaos[0].value == 250


async def test_upstream_unreachable_returns_502_recorded(tmp_path: Path) -> None:
    out = tmp_path / "t.jsonl"
    policy = ChaosPolicy()  # pure forward

    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    proxy, _ = _make_proxy(out, policy, handler)
    resp = await proxy.handle("POST", "/tools/get_order", {}, b'{"order_id":"1"}')
    await proxy.aclose()

    assert resp.status == 502
    events = list(read_trace(out))
    responses = [e for e in events if isinstance(e, ToolResponse)]
    assert len(responses) == 1
    assert responses[0].status == 502


async def test_non_json_body_recorded_as_none(tmp_path: Path) -> None:
    out = tmp_path / "t.jsonl"

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json", headers={"content-type": "text/plain"})

    proxy, _ = _make_proxy(out, ChaosPolicy(), handler)
    await proxy.handle("POST", "/tools/get_order", {}, b"not json")
    await proxy.aclose()

    events = list(read_trace(out))
    responses = [e for e in events if isinstance(e, ToolResponse)]
    assert responses[0].body is None
    assert responses[0].args_hash is None


async def test_seed_reproducible_injection_pattern(tmp_path: Path) -> None:
    policy = ChaosPolicy(
        targets=[ChaosTarget(tool="get_order",
                             policy=ToolChaosPolicy(failure_rate=0.5, status_code=500))]
    )

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    async def pattern(out: Path) -> list[bool]:
        proxy, _ = _make_proxy(out, policy, handler, seed=7)
        results = []
        for _ in range(20):
            r = await proxy.handle("POST", "/tools/get_order", {}, b'{"order_id":"1"}')
            results.append(r.status == 500)
        await proxy.aclose()
        return results

    p1 = await pattern(tmp_path / "a.jsonl")
    p2 = await pattern(tmp_path / "b.jsonl")
    assert p1 == p2
    assert any(p1) and not all(p1)
