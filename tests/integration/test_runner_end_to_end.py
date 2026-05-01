"""End-to-end runner tests against an in-process FastAPI agent server."""
from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from agentchaos.runner import RunCoordinator
from agentchaos.scenario.schema import AgentTarget, Scenario, UserTurn
from agentchaos.trace.reader import read_trace
from agentchaos.trace.schema import (
    AgentTurn,
    ModelCall,
    RunEnd,
    RunMeta,
    SessionEnd,
    SessionStart,
    ToolCall,
)
from agentchaos.trace.schema import (
    UserTurn as UserTurnEvent,
)
from agentchaos.transport import HTTPTransport
from agentchaos.transport.base import FidelityTier

pytestmark = pytest.mark.integration


def _scenario(endpoint: str, turns: list[str]) -> Scenario:
    return Scenario(
        id="t",
        name="t",
        agent=AgentTarget(endpoint=endpoint),  # type: ignore[arg-type]
        conversation=[UserTurn(user=u) for u in turns],
    )


def _full_response(message: str) -> dict:
    return {
        "session_id": "s",
        "message": message,
        "agent": {"name": "a", "version": "1", "model": "gpt-4o-mini"},
        "events": [
            {
                "type": "model_call",
                "name": "planner",
                "model": "gpt-4o-mini",
                "input_tokens": 100,
                "output_tokens": 20,
                "cost_usd": 0.001,
                "latency_ms": 200,
                "metadata": {"rag_chunks": 5},
            },
            {
                "type": "tool_call",
                "name": "get_order",
                "args": {"order_id": "12345"},
                "latency_ms": 50,
                "result_summary": "ok",
                "retries": 0,
            },
        ],
        "usage": {"input_tokens": 100, "output_tokens": 20, "cost_usd": 0.001},
    }


async def test_full_fidelity_three_turns(tmp_path: Path) -> None:
    counter = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        return httpx.Response(200, json=_full_response(f"ack {counter['n']}"))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5)
    sc = _scenario("http://test.local/chat", ["a", "b", "c"])
    transport = HTTPTransport(sc.agent, client=client)
    coordinator = RunCoordinator(sc, transport)

    out = tmp_path / "run.jsonl"
    result = await coordinator.run_once(out)
    await transport.aclose()
    await client.aclose()

    assert out.exists()
    events = list(read_trace(out))
    # First and last event types
    assert isinstance(events[0], RunMeta)
    assert isinstance(events[-1], RunEnd)
    # Session start and end appear once each
    assert sum(isinstance(e, SessionStart) for e in events) == 1
    assert sum(isinstance(e, SessionEnd) for e in events) == 1
    # 3 user turns + 3 agent turns
    assert sum(isinstance(e, UserTurnEvent) for e in events) == 3
    assert sum(isinstance(e, AgentTurn) for e in events) == 3
    # Each turn produced 1 model_call + 1 tool_call
    assert sum(isinstance(e, ModelCall) for e in events) == 3
    assert sum(isinstance(e, ToolCall) for e in events) == 3
    # Run summary
    assert result.session.outcome == "completed"
    assert result.session.tool_calls == 3
    assert result.session.model_calls == 3
    assert result.session.fidelity is FidelityTier.FULL
    assert result.session.total_cost_usd is not None
    assert result.session.total_cost_usd > 0


async def test_seq_monotonic_and_starts_at_zero(tmp_path: Path) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_full_response("ok"))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5)
    sc = _scenario("http://test.local/chat", ["a"])
    transport = HTTPTransport(sc.agent, client=client)
    out = tmp_path / "run.jsonl"
    await RunCoordinator(sc, transport).run_once(out)
    await transport.aclose()
    await client.aclose()

    events = list(read_trace(out))
    seqs = [e.seq for e in events]
    assert seqs[0] == 0
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)


async def test_session_terminates_on_transport_error(tmp_path: Path) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5)
    sc = _scenario("http://test.local/chat", ["a", "b", "c"])
    transport = HTTPTransport(sc.agent, client=client)

    out = tmp_path / "run.jsonl"
    result = await RunCoordinator(sc, transport).run_once(out)
    await transport.aclose()
    await client.aclose()

    assert result.session.outcome == "error"
    assert result.session.error is not None
    assert "http_500" in result.session.error
    # Should have stopped before processing all 3 turns.
    events = list(read_trace(out))
    user_turns = [e for e in events if isinstance(e, UserTurnEvent)]
    assert len(user_turns) == 1
    run_end = events[-1]
    assert isinstance(run_end, RunEnd)
    assert run_end.outcome == "fail"
    assert run_end.exit_code == 4


async def test_aggregate_fidelity_propagates(tmp_path: Path) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": "hi",
                "tool_calls": [
                    {"name": "get_order", "args": {"id": "1"}, "latency_ms": 50},
                ],
                "usage": {"input_tokens": 100, "output_tokens": 20, "cost_usd": 0.001},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5)
    sc = _scenario("http://test.local/chat", ["hi"])
    transport = HTTPTransport(sc.agent, client=client)
    out = tmp_path / "run.jsonl"
    result = await RunCoordinator(sc, transport).run_once(out)
    await transport.aclose()
    await client.aclose()

    assert result.session.fidelity is FidelityTier.AGGREGATE
    events = list(read_trace(out))
    tool_calls = [e for e in events if isinstance(e, ToolCall)]
    assert len(tool_calls) == 1


async def test_message_only_fidelity_marks_cost_unknown(tmp_path: Path) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": "ok"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5)
    sc = _scenario("http://test.local/chat", ["hi"])
    transport = HTTPTransport(sc.agent, client=client)
    out = tmp_path / "run.jsonl"
    result = await RunCoordinator(sc, transport).run_once(out)
    await transport.aclose()
    await client.aclose()

    assert result.session.fidelity is FidelityTier.MESSAGE_ONLY
    assert result.session.total_cost_usd is None
    events = list(read_trace(out))
    assert sum(isinstance(e, ModelCall) for e in events) == 0
    assert sum(isinstance(e, ToolCall) for e in events) == 0


def test_synchronous_run() -> None:
    """Verify the API is callable from sync code via asyncio.run."""
    async def go(tmp: Path) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"message": "ok"})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5)
        sc = _scenario("http://test.local/chat", ["x"])
        transport = HTTPTransport(sc.agent, client=client)
        await RunCoordinator(sc, transport).run_once(tmp / "x.jsonl")
        await transport.aclose()
        await client.aclose()

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(go(Path(tmp)))
