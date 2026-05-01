"""Orchestrate one full run: open trace, run session, close trace."""
from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from agentchaos import __version__
from agentchaos.runner.session import Session, SessionResult
from agentchaos.scenario.loader import scenario_hash
from agentchaos.scenario.schema import Scenario
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


class RunCoordinator:
    """Coordinate one scenario run end-to-end."""

    def __init__(
        self,
        scenario: Scenario,
        transport: AgentTransport,
        *,
        seed: int | None = None,
    ) -> None:
        self._scenario = scenario
        self._transport = transport
        self._seed = seed

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

        recorder = TraceRecorder(out)
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
                    seed=self._seed,
                    started_at=started_at,
                )
            )
            session = Session(
                run_id=run_id,
                session_id=session_id,
                scenario=self._scenario,
                transport=self._transport,
                recorder=recorder,
                next_seq=1,
            )
            session_result = await session.run()
            outcome_lit: Literal["pass", "fail"] = (
                "pass" if session_result.error is None else "fail"
            )
            exit_code = 0 if session_result.error is None else 4
            recorder.write(
                RunEnd(
                    run_id=run_id,
                    seq=session.next_seq,
                    timestamp=datetime.now(UTC),
                    outcome=outcome_lit,
                    finished_at=datetime.now(UTC),
                    exit_code=exit_code,
                )
            )
        finally:
            recorder.close()

        return RunResult(
            run_id=run_id,
            trace_path=out,
            session=session_result,
            duration_s=time.perf_counter() - t0,
        )
