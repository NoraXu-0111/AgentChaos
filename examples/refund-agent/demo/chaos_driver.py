"""Reusable in-process chaos driver.

Chaos MUST run in-process: ``RunCoordinator`` starts the chaos proxy and rewrites
``TOOLS_BASE_URL`` inside *its own* process, so a separately-spawned agent would
never route through the proxy. This module serves a given agent app AND the
tools app on background threads, then drives the coordinator against them.

``run_chaos(agent_app, ...)`` returns ``(report_text, trace, exit_code)``.
"""
from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

import httpx
import uvicorn

HERE = Path(__file__).resolve().parent
REFUND_DIR = HERE.parent
REPO_ROOT = REFUND_DIR.parent.parent
for p in (str(REFUND_DIR), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from agentchaos.chaos.policy import ChaosPolicy, ChaosTarget, ToolChaosPolicy  # noqa: E402
from agentchaos.profile.metrics import aggregate  # noqa: E402
from agentchaos.report.terminal import render_terminal  # noqa: E402
from agentchaos.runner.coordinator import RunCoordinator  # noqa: E402
from agentchaos.scenario.schema import AgentTarget, Scenario, UserTurn  # noqa: E402
from agentchaos.trace.reader import read_trace  # noqa: E402
from agentchaos.trace.schema import AgentTurn as AgentTurnEvent  # noqa: E402
from agentchaos.trace.schema import ChaosInjected  # noqa: E402
from agentchaos.transport.http import HTTPTransport  # noqa: E402
from agentchaos.verdict import compute_verdict  # noqa: E402


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def serve(app: object, port: int) -> uvicorn.Server:
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")  # type: ignore[arg-type]
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 8
    while time.time() < deadline:
        try:
            httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5)
            return server
        except Exception:
            time.sleep(0.05)
    raise RuntimeError(f"server on :{port} failed to start")


def chaos_scenario(endpoint: str, *, name: str = "refund-chaos-get-order") -> Scenario:
    # failure_rate=1.0 guarantees the fault+fallback fires for the demo; the seed
    # keeps it reproducible. Story = inject 503 on get_order, expect graceful degrade.
    return Scenario(
        id=name,
        name=name,
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


async def run_chaos(
    agent_app: object,
    tools_app: object,
    out: Path,
    *,
    scenario_name: str = "refund-chaos-get-order",
) -> tuple[str, list, int]:
    """Serve both apps in-process, run one chaos scenario, return report+trace+exit."""
    agent_port = free_port()
    tools_port = free_port()
    agent_srv = serve(agent_app, agent_port)
    tools_srv = serve(tools_app, tools_port)
    agent_url = f"http://127.0.0.1:{agent_port}"
    tools_url = f"http://127.0.0.1:{tools_port}"
    try:
        httpx.post(f"{agent_url}/control/reset", timeout=2.0)
        sc = chaos_scenario(f"{agent_url}/chat", name=scenario_name)
        transport = HTTPTransport(sc.agent)
        coordinator = RunCoordinator(sc, transport, tools_base_url=tools_url)
        try:
            result = await coordinator.run_once(out)
        finally:
            await transport.aclose()
    finally:
        agent_srv.should_exit = True
        tools_srv.should_exit = True
        time.sleep(0.2)

    trace = list(read_trace(result.trace_path))
    metrics = aggregate(trace)
    verdict = compute_verdict(
        metrics,
        sc.expect,
        sc.budgets,
        final_text=result.session.final_text,
        session_error=result.session.error,
        chaos=sc.chaos,
        trace=trace,
    )
    report = render_terminal(
        scenario_name=sc.name,
        verdict=verdict,
        metrics=metrics,
        diff=None,
        causes=[],
        trace_path=result.trace_path,
    )

    chaos_events = [e for e in trace if isinstance(e, ChaosInjected)]
    turns = [e for e in trace if isinstance(e, AgentTurnEvent)]
    final_text = turns[-1].text if turns else ""
    lines = [report, "", "Chaos injected:"]
    if chaos_events:
        for e in chaos_events:
            lines.append(f"  - {e.tool_name}: {e.injection_type}={e.value} (policy {e.policy})")
    else:
        lines.append("  (none fired)")
    lines.append("")
    if verdict.exit_code == 0:
        lines.append("Fallback path observed:")
        lines.append(f'  agent final reply → "{final_text}"')
    else:
        lines.append("Fallback FAILED — agent did not degrade gracefully under the fault.")
        if result.session.error:
            lines.append(f"  session error: {result.session.error}")
    lines.append("")
    lines.append(f"Seed: {sc.chaos.seed}   exit={verdict.exit_code}")
    return "\n".join(lines), trace, verdict.exit_code
