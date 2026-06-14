"""End-to-end chaos: real tool server + chaos proxy + demo agent.

The demo agent makes real outbound HTTP tool calls to ``TOOLS_BASE_URL``. The
coordinator starts the chaos proxy and overrides ``TOOLS_BASE_URL`` to point the
agent at the proxy, forwarding survivors to the real tool server below.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn

from agentchaos.chaos.policy import ChaosPolicy, ChaosTarget, ToolChaosPolicy
from agentchaos.runner.coordinator import RunCoordinator
from agentchaos.scenario.schema import AgentTarget, Scenario, UserTurn
from agentchaos.trace.reader import read_trace
from agentchaos.trace.schema import AgentTurn as AgentTurnEvent
from agentchaos.trace.schema import ChaosInjected
from agentchaos.transport.http import HTTPTransport

pytestmark = pytest.mark.integration


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _serve(app: object, port: int) -> uvicorn.Server:
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")  # type: ignore[arg-type]
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5)
            return server
        except Exception:
            time.sleep(0.05)
    raise RuntimeError(f"server on :{port} failed to start")


@pytest.fixture(scope="module")
def servers() -> Iterator[tuple[str, str]]:
    repo_root = Path(__file__).resolve().parent.parent.parent
    demo_dir = repo_root / "examples" / "refund-agent"
    sys.path.insert(0, str(demo_dir))
    try:
        from server.main import app as agent_app  # type: ignore[import-not-found]
        from tools.main import app as tools_app  # type: ignore[import-not-found]
    finally:
        sys.path.pop(0)

    agent_port = _free_port()
    tools_port = _free_port()
    agent_srv = _serve(agent_app, agent_port)
    tools_srv = _serve(tools_app, tools_port)
    yield f"http://127.0.0.1:{agent_port}", f"http://127.0.0.1:{tools_port}"
    agent_srv.should_exit = True
    tools_srv.should_exit = True
    time.sleep(0.2)


def _scenario(endpoint: str) -> Scenario:
    return Scenario(
        id="refund-chaos",
        name="refund-chaos",
        agent=AgentTarget(endpoint=endpoint),  # type: ignore[arg-type]
        conversation=[
            UserTurn(user="I want to return my order."),
            UserTurn(user="My order number is 12345."),
        ],
        chaos=ChaosPolicy(
            seed=42,
            expect_fallback=True,
            targets=[
                ChaosTarget(
                    tool="get_order",
                    policy=ToolChaosPolicy(failure_rate=1.0, status_code=503),
                )
            ],
        ),
    )


async def _run(agent_url: str, tools_url: str, out: Path) -> list:
    httpx.post(f"{agent_url}/control/reset", timeout=2.0)
    sc = _scenario(f"{agent_url}/chat")
    transport = HTTPTransport(sc.agent)
    coordinator = RunCoordinator(sc, transport, tools_base_url=tools_url)
    await coordinator.run_once(out)
    await transport.aclose()
    return list(read_trace(out))


async def test_chaos_injected_and_fallback_observable(
    tmp_path: Path, servers: tuple[str, str]
) -> None:
    agent_url, tools_url = servers
    prior = os.environ.get("TOOLS_BASE_URL")
    try:
        events = await _run(agent_url, tools_url, tmp_path / "run.jsonl")
    finally:
        if prior is None:
            os.environ.pop("TOOLS_BASE_URL", None)
        else:
            os.environ["TOOLS_BASE_URL"] = prior

    chaos = [e for e in events if isinstance(e, ChaosInjected)]
    assert any(e.tool_name == "get_order" for e in chaos)
    assert len(chaos) >= 1

    agent_turns = [e for e in events if isinstance(e, AgentTurnEvent)]
    final_text = agent_turns[-1].text if agent_turns else ""
    assert "human agent will follow up" in final_text


async def test_chaos_reproducible_across_runs(
    tmp_path: Path, servers: tuple[str, str]
) -> None:
    agent_url, tools_url = servers
    prior = os.environ.get("TOOLS_BASE_URL")
    try:
        ev1 = await _run(agent_url, tools_url, tmp_path / "r1.jsonl")
        ev2 = await _run(agent_url, tools_url, tmp_path / "r2.jsonl")
    finally:
        if prior is None:
            os.environ.pop("TOOLS_BASE_URL", None)
        else:
            os.environ["TOOLS_BASE_URL"] = prior

    def positions(events: list) -> list[tuple[str, str]]:
        return [
            (e.tool_name, e.injection_type)
            for e in events
            if isinstance(e, ChaosInjected)
        ]

    p1, p2 = positions(ev1), positions(ev2)
    assert p1 == p2
    assert len(p1) == len(p2)
