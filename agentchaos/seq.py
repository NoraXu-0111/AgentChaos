"""Shared monotonic sequence counter for trace events.

Both the session driver and the chaos proxy run in the same event loop but emit
events into the same trace. A single shared counter keeps ``seq`` globally
monotonic and unique. ``take()`` is lock-guarded for safety even though there is
only one event loop.
"""
from __future__ import annotations

import threading


class SeqCounter:
    """Hand out monotonically increasing, unique sequence numbers."""

    def __init__(self, start: int = 0) -> None:
        self._next = start
        self._lock = threading.Lock()

    def take(self) -> int:
        """Return the next sequence number and advance the counter."""
        with self._lock:
            value = self._next
            self._next += 1
            return value

    @property
    def value(self) -> int:
        """The next value ``take()`` would return. No side effect."""
        return self._next
