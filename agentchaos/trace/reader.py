"""JSONL trace reader.

Yields typed ``TraceEvent`` objects. A truncated last line is silently skipped
so partially-written traces (e.g. from a crash mid-write) remain parseable.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from agentchaos.trace.schema import TraceEvent, parse_event


class TraceReadError(Exception):
    """Raised when a non-final line in a trace cannot be parsed."""


def read_trace(path: str | Path) -> Iterator[TraceEvent]:
    """Yield typed events from a JSONL trace file."""
    p = Path(path)
    with p.open("r") as fh:
        lines = fh.readlines()
    last_idx = len(lines) - 1
    for idx, raw in enumerate(lines):
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError as exc:
            if idx == last_idx:
                # Tolerate a partial last line (e.g. crash mid-write).
                return
            raise TraceReadError(f"{p}:{idx + 1}: invalid JSON — {exc}") from exc
        yield parse_event(data)
