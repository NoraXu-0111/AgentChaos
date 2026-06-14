"""Orchestrate one full run: open trace, run session, close trace.

When the scenario declares a chaos policy with targets, the coordinator starts
an in-process chaos proxy, points the agent at it via the ``TOOLS_BASE_URL``
environment variable, threads a shared :class:`SeqCounter` into both the session
and the proxy so all events share one monotonic sequence, and writes chaos
events into the same recorder.
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from agentchaos import __version__
from agentchaos.chaos.proxy import ChaosProxy
from agentchaos.chaos.server import ChaosProxyServer
from agentchaos.runner.session import Session, SessionResult
from agentchaos.scenario.loader import scenario_hash
from agentchaos.scenario.schema import Scenario
from agentchaos.seq import SeqCounter
from agentchaos.trace.recorder import TraceRecorder
from agentchaos.trace.schema import RunEnd, RunMeta
from agentchaos.transport.base import AgentTransport


class RunResult(BaseModel):
    """Aggregate result of one full run."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    run_id: str
    trace_path: Path
    session: SessionResult
    duration_s: float
    seed: int | None = None


class RunCoordinator:
    """Coordinate one scenario run end-to-end."""

    def __init__(
        self,
        scenario: Scenario,
        transport: AgentTransport,
        *,
        seed: int | None = None,
        tools_base_url: str | None = None,
    ) -> None:
        self._scenario = scenario
        self._transport = transport
        self._seed = seed
        # Real upstream tool server the proxy forwards survivors to.
        self._tools_base_url = tools_base_url or os.environ.get(
            "TOOLS_UPSTREAM_URL", "http://127.0.0.1:8090"
        )

    def _effective_seed(self) -> int:
        """Resolve the chaos seed: chaos.seed → scenario.seed → CLI seed → random."""
        chaos = self._scenario.chaos
        if chaos is not None and chaos.seed is not None:
            return chaos.seed
        if self._scenario.seed is not None:
            return self._scenario.seed
        if self._seed is not None:
            return self._seed
        return int.from_bytes(os.urandom(4), "big")

    async def run_once(
        self,
        out_path: str | Path,
        *,
        scenario_path: str | None = None,
    ) -> RunResult:
        out = Path(out_path)
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        session_id = f"s-{uuid.uuid4().hex[:8]}"
        started_at = datetime.now(UTC)
        t0 = time.perf_counter()

        chaos = self._scenario.chaos
        chaos_active = chaos is not None and len(chaos.targets) > 0
        seq = SeqCounter(start=1)

        recorded_seed: int | None = self._seed
        if chaos_active:
            recorded_seed = self._effective_seed()
            print(f"chaos seed: {recorded_seed}")

        recorder = TraceRecorder(out)
        server: ChaosProxyServer | None = None
        prior_tools_url = os.environ.get("TOOLS_BASE_URL")
        try:
            recorder.write(
                RunMeta(
                    run_id=run_id,
                    seq=0,
                    timestamp=started_at,
                    agentchaos_version=__version__,
                    scenario_path=scenario_path or "<inline>",
                    scenario_hash=scenario_hash(self._scenario),
                    scenario_name=self._scenario.name,
                    seed=recorded_seed,
                    started_at=started_at,
                )
            )

            if chaos_active and chaos is not None:
                proxy = ChaosProxy(
                    upstream_base_url=self._tools_base_url,
                    policy=chaos,
                    seed=recorded_seed if recorded_seed is not None else 0,
                    recorder=recorder,
                    seq=seq,
                    run_id=run_id,
                    session_id=session_id,
                )
                server = ChaosProxyServer(proxy)
                base_url = await server.start()
                os.environ["TOOLS_BASE_URL"] = base_url

            session = Session(
                run_id=run_id,
                session_id=session_id,
                scenario=self._scenario,
                transport=self._transport,
                recorder=recorder,
                seq=seq,
            )
            session_result = await session.run()
            outcome_lit: Literal["pass", "fail"] = (
                "pass" if session_result.error is None else "fail"
            )
            exit_code = 0 if session_result.error is None else 4
            recorder.write(
                RunEnd(
                    run_id=run_id,
                    seq=seq.take(),
                    timestamp=datetime.now(UTC),
                    outcome=outcome_lit,
                    finished_at=datetime.now(UTC),
                    exit_code=exit_code,
                )
            )
        finally:
            if server is not None:
                await server.stop()
                if prior_tools_url is None:
                    os.environ.pop("TOOLS_BASE_URL", None)
                else:
                    os.environ["TOOLS_BASE_URL"] = prior_tools_url
            recorder.close()

        return RunResult(
            run_id=run_id,
            trace_path=out,
            session=session_result,
            duration_s=time.perf_counter() - t0,
            seed=recorded_seed,
        )
