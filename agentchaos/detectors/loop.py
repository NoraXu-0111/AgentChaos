"""Loop detector — flags repeated identical tool calls inside a window."""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from agentchaos.detectors.schema import Finding, Severity
from agentchaos.trace.schema import ToolCall, TraceEvent


def detect_loops(
    trace: Iterable[TraceEvent],
    *,
    window: int = 5,
    threshold: int = 3,
) -> list[Finding]:
    """Detect ``(name, args_hash)`` repeats inside a sliding window.

    For each contiguous slice of ``window`` consecutive ``ToolCall`` events,
    count occurrences of every ``(name, args_hash)`` signature; emit one
    :class:`Finding` per distinct signature that hits ``threshold``. Each
    signature is reported at most once across the whole pass.

    If the trace contains fewer than ``window`` tool calls, the whole list is
    scanned as a single window. Empty traces yield ``[]``.
    """
    if window < 1:
        raise ValueError(f"window must be >= 1, got {window}")
    if threshold < 2:
        raise ValueError(f"threshold must be >= 2, got {threshold}")

    tool_calls: list[ToolCall] = [ev for ev in trace if isinstance(ev, ToolCall)]
    if not tool_calls:
        return []

    seen: dict[tuple[str, str], Finding] = {}

    effective_window = window if len(tool_calls) >= window else len(tool_calls)
    for start in range(0, len(tool_calls) - effective_window + 1):
        slice_ = tool_calls[start : start + effective_window]
        counts: Counter[tuple[str, str]] = Counter(
            (tc.name, tc.args_hash) for tc in slice_
        )
        for sig, count in counts.items():
            if count < threshold:
                continue
            if sig in seen:
                # Keep the strongest (highest count) instance.
                existing = seen[sig]
                if count <= existing.evidence["count"]:
                    continue
            seqs = [tc.seq for tc in slice_ if (tc.name, tc.args_hash) == sig]
            severity: Severity = "high" if count > threshold else "warn"
            name, args_hash = sig
            seen[sig] = Finding(
                detector="loop",
                severity=severity,
                description=(
                    f"{name} called {count}x with identical args_hash "
                    f"within a window of {effective_window} (threshold {threshold})"
                ),
                evidence={
                    "tool": name,
                    "args_hash": args_hash,
                    "count": count,
                    "window": effective_window,
                    "threshold": threshold,
                    "first_seq": min(seqs),
                    "last_seq": max(seqs),
                },
            )

    return list(seen.values())
