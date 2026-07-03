#!/usr/bin/env python
"""Run the same chaos scenario against the BROKEN agent (no fallback).

The agent crashes under the injected 503, so AgentChaos fails the run with a
non-zero exit code — the reliability regression a CI chaos gate must block.
Writes caps/C_broken.txt. Exits with the run's real exit code.

Usage: uv run --project <repo_root> python examples/refund-agent/demo/run_broken_chaos.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from broken_agent import app as broken_app  # noqa: E402
from chaos_driver import run_chaos  # noqa: E402
from tools.main import app as tools_app  # type: ignore[import-not-found]  # noqa: E402


async def main() -> int:
    out_dir = HERE / "runs"
    caps_dir = HERE / "caps"
    out_dir.mkdir(exist_ok=True)
    caps_dir.mkdir(exist_ok=True)
    report, _trace, code = await run_chaos(
        broken_app, tools_app, out_dir / "chaos_broken.jsonl",
        scenario_name="refund-chaos-broken-fallback",
    )
    (caps_dir / "C_broken.txt").write_text(report + "\n")
    print(report)
    return code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
