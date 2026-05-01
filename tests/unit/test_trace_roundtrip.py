"""Tests for TraceRecorder + read_trace round-trip and partial-file handling."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from agentchaos.trace import (
    AgentTurn,
    ModelCall,
    RunEnd,
    RunMeta,
    SessionEnd,
    SessionStart,
    ToolCall,
    TraceRecorder,
    UserTurn,
    parse_event,
    read_trace,
)
from agentchaos.trace.reader import TraceReadError


def _ts(seq: int) -> datetime:
    return datetime(2026, 4, 30, 12, 0, seq, tzinfo=UTC)


def _build_full_trace(run_id: str = "run-1") -> list:
    return [
        RunMeta(
            run_id=run_id,
            seq=0,
            timestamp=_ts(0),
            agentchaos_version="0.1.0.dev0",
            scenario_path="scenarios/refund.yaml",
            scenario_hash="sha256:abc",
            scenario_name="refund",
            started_at=_ts(0),
        ),
        SessionStart(
            run_id=run_id,
            seq=1,
            timestamp=_ts(1),
            session_id="s-1",
            scenario_name="refund",
            agent_target={"type": "http", "endpoint": "http://localhost:8080/chat"},
        ),
        UserTurn(
            run_id=run_id, seq=2, timestamp=_ts(2),
            session_id="s-1", turn_index=0, text="hi",
        ),
        ModelCall(
            run_id=run_id, seq=3, timestamp=_ts(3), session_id="s-1",
            turn_index=0, call_index=0, name="planner", model="gpt-4o-mini",
            input_tokens=100, output_tokens=20, cost_usd=0.0001, latency_ms=200,
            metadata={"rag_chunks": 5},
        ),
        ToolCall(
            run_id=run_id, seq=4, timestamp=_ts(4), session_id="s-1",
            turn_index=0, call_index=1, name="get_order",
            args={"order_id": "12345"}, args_hash="sha256:xyz",
            latency_ms=100, result_summary="ok", retries=0,
        ),
        AgentTurn(
            run_id=run_id, seq=5, timestamp=_ts(5), session_id="s-1",
            turn_index=0, text="here's your order", latency_ms=320,
            agent={"name": "refund", "version": "0.1", "model": "gpt-4o-mini"},
            usage={"input_tokens": 100, "output_tokens": 20, "cost_usd": 0.0001},
        ),
        SessionEnd(
            run_id=run_id, seq=6, timestamp=_ts(6), session_id="s-1",
            outcome="completed", turns=1, tool_calls=1, model_calls=1, retries=0,
            total_cost_usd=0.0001, total_latency_ms=320, duration_s=0.32,
        ),
        RunEnd(
            run_id=run_id, seq=7, timestamp=_ts(7), outcome="pass",
            finished_at=_ts(7), exit_code=0,
        ),
    ]


def test_recorder_roundtrip(tmp_path: Path) -> None:
    out = tmp_path / "trace.jsonl"
    events = _build_full_trace()
    with TraceRecorder(out) as rec:
        for e in events:
            rec.write(e)
    read_back = list(read_trace(out))
    assert len(read_back) == len(events)
    for original, parsed in zip(events, read_back, strict=True):
        assert original.model_dump(mode="json") == parsed.model_dump(mode="json")


def test_recorder_creates_parent_dir(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "trace.jsonl"
    rec = TraceRecorder(nested)
    rec.close()
    assert nested.exists()


def test_reader_skips_blank_lines(tmp_path: Path) -> None:
    out = tmp_path / "trace.jsonl"
    events = _build_full_trace()
    with TraceRecorder(out) as rec:
        for e in events:
            rec.write(e)
    # inject blank lines
    raw = out.read_text()
    out.write_text("\n\n" + raw + "\n\n")
    assert len(list(read_trace(out))) == len(events)


def test_reader_tolerates_truncated_last_line(tmp_path: Path) -> None:
    out = tmp_path / "trace.jsonl"
    events = _build_full_trace()
    with TraceRecorder(out) as rec:
        for e in events:
            rec.write(e)
    # truncate the last 5 chars to simulate a crash mid-write
    raw = out.read_text()
    out.write_text(raw[:-5])
    parsed = list(read_trace(out))
    assert len(parsed) == len(events) - 1


def test_reader_raises_on_non_final_corruption(tmp_path: Path) -> None:
    out = tmp_path / "trace.jsonl"
    out.write_text("not valid json\n{}\n")
    with pytest.raises(TraceReadError):
        list(read_trace(out))


def test_schema_version_preserved(tmp_path: Path) -> None:
    out = tmp_path / "t.jsonl"
    events = _build_full_trace()
    with TraceRecorder(out) as rec:
        for e in events:
            rec.write(e)
    for line in out.read_text().splitlines():
        assert '"schema_version":"1"' in line


def test_parse_event_dispatches_on_kind() -> None:
    raw = {
        "schema_version": "1",
        "run_id": "r",
        "seq": 0,
        "timestamp": "2026-04-30T12:00:00Z",
        "kind": "user_turn",
        "session_id": "s-1",
        "turn_index": 0,
        "text": "hello",
    }
    ev = parse_event(raw)
    assert isinstance(ev, UserTurn)
    assert ev.text == "hello"


def test_parse_event_rejects_unknown_kind() -> None:
    raw = {
        "schema_version": "1",
        "run_id": "r",
        "seq": 0,
        "timestamp": "2026-04-30T12:00:00Z",
        "kind": "not_a_kind",
    }
    with pytest.raises(Exception):
        parse_event(raw)
