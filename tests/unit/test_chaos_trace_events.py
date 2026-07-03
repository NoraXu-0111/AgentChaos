"""Round-trip tests for the chaos trace events."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from agentchaos.trace.reader import read_trace
from agentchaos.trace.recorder import TraceRecorder
from agentchaos.trace.schema import ChaosInjected, RunEnd, ToolResponse, parse_event


def _now() -> datetime:
    return datetime.now(UTC)


def test_chaos_injected_round_trips() -> None:
    ev = ChaosInjected(
        run_id="run-1",
        seq=3,
        timestamp=_now(),
        target="get_order",
        policy="failure_rate=0.5 status_code=503",
        injection_type="status_code",
        value=503,
        tool_name="get_order",
        args_hash="sha256:abc",
    )
    parsed = parse_event(json.loads(ev.model_dump_json()))
    assert isinstance(parsed, ChaosInjected)
    assert parsed.injection_type == "status_code"
    assert parsed.value == 503


def test_tool_response_reads_back(tmp_path: Path) -> None:
    out = tmp_path / "trace.jsonl"
    rec = TraceRecorder(out)
    rec.write(
        ToolResponse(
            run_id="run-1",
            seq=4,
            timestamp=_now(),
            tool_name="get_order",
            status=200,
            size_bytes=42,
            headers_subset={"content-type": "application/json"},
            body={"order_id": "123"},
            chaos_injected=False,
        )
    )
    rec.write(RunEnd(run_id="run-1", seq=5, timestamp=_now(), outcome="pass",
                     finished_at=_now(), exit_code=0))
    rec.close()

    events = list(read_trace(out))
    tr = events[0]
    assert isinstance(tr, ToolResponse)
    assert tr.status == 200
    assert tr.body == {"order_id": "123"}
    assert tr.chaos_injected is False


def test_bad_injection_type_rejected() -> None:
    with pytest.raises(ValidationError):
        ChaosInjected(
            run_id="r",
            seq=1,
            timestamp=_now(),
            target="t",
            policy="p",
            injection_type="explode",  # type: ignore[arg-type]
            value=1,
            tool_name="t",
        )


def test_tool_response_negative_size_rejected() -> None:
    with pytest.raises(ValidationError):
        ToolResponse(
            run_id="r",
            seq=1,
            timestamp=_now(),
            tool_name="t",
            status=200,
            size_bytes=-1,
        )
