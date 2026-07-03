#!/usr/bin/env python
"""Scenario B — seeded chaos, in-process (good agent degrades gracefully).

Injects a guaranteed 503 on get_order against the REAL refund agent; the agent
must take its observable fallback path ("a human agent will follow up") instead
of crashing → PASS, exit 0. Then runs a second time with the same seed to prove
the injected faults are reproducible.

Writes caps/B1_chaos.txt and caps/B2_reproduce.txt.

Usage: uv run --project <repo_root> python examples/refund-agent/demo/run_scenarioB.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from chaos_driver import run_chaos  # noqa: E402
from tools.main import app as tools_app  # type: ignore[import-not-found]  # noqa: E402


async def main() -> int:
    from server.main import app as agent_app  # type: ignore[import-not-found]

    out_dir = HERE / "runs"
    caps_dir = HERE / "caps"
    out_dir.mkdir(exist_ok=True)
    caps_dir.mkdir(exist_ok=True)

    report1, tr1, code1 = await run_chaos(agent_app, tools_app, out_dir / "chaos1.jsonl")
    report2, tr2, code2 = await run_chaos(agent_app, tools_app, out_dir / "chaos2.jsonl")

    (caps_dir / "B1_chaos.txt").write_text(report1 + "\n")
    print(report1)
    print("\n" + "=" * 60 + "\n")

    from chaos_driver import ChaosInjected  # noqa: E402

    def positions(trace: list) -> list[tuple[str, str, int]]:
        return [
            (e.tool_name, e.injection_type, e.value)
            for e in trace
            if isinstance(e, ChaosInjected)
        ]

    p1, p2 = positions(tr1), positions(tr2)
    repro = p1 == p2 and len(p1) > 0
    repro_lines = [
        "AgentChaos — chaos reproducibility (seed=42)",
        "",
        f"Run 1 injections: {p1}",
        f"Run 2 injections: {p2}",
        "",
        f"Identical across runs: {'YES (deterministic)' if repro else 'NO'}",
        "",
        "Same seed -> same faults -> same verdict. Replayable in CI.",
    ]
    repro_report = "\n".join(repro_lines)
    (caps_dir / "B2_reproduce.txt").write_text(repro_report + "\n")
    print(repro_report)

    return 0 if (code1 == 0 and repro) else 3


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
