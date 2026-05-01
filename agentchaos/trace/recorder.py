"""Synchronous JSONL trace recorder. One event per line, flushed per write."""
from __future__ import annotations

from pathlib import Path
from types import TracebackType
from typing import IO

from agentchaos.trace.schema import TraceEvent


class TraceRecorder:
    """Append-only JSONL writer for trace events.

    The recorder does not own ``run_id`` or ``seq`` — callers stamp those on
    each event before writing. This keeps the recorder dumb and trivial to test.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fh: IO[str] = self._path.open("w")

    def write(self, event: TraceEvent) -> None:
        """Serialize one event to JSON and append as a single line."""
        line = event.model_dump_json()
        self._fh.write(line + "\n")
        self._fh.flush()

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()

    @property
    def path(self) -> Path:
        return self._path

    def __enter__(self) -> TraceRecorder:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
