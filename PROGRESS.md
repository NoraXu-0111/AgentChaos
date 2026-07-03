# AgentChaos v0 — overnight build progress

Started: 2026-04-30 evening, working autonomously.
Plan: implement Phases 0-8 from `/Users/noraxu/Desktop/Finance/AgentChaos/13 - v0 Refined Plan.md`.

## Status

All phases 0-8 complete. Full suite green (123 tests passing).

| Phase | Title | Status | Notes |
|-------|-------|--------|-------|
| 0 | Repo bootstrap | done | CLI skeleton, CI |
| 1 | Scenario + Budget schemas | done | hashing, absolute & regression checks |
| 2 | Trace + Transport | done | schema/recorder/reader, HTTPTransport (3-tier fidelity) |
| 3 | Runner | done | Session + RunCoordinator, end-to-end vs MockTransport |
| 4 | Metrics | done | aggregate(trace) -> by_model, by_tool, tool_sequence |
| 5 | Compare + Causes | done | compare + cause detection |
| 6 | Verdict + Terminal report | done | — |
| 7 | CLI wiring | done | init / doctor / run / compare |
| 8 | Demo + README | done | refund-agent example + e2e demo test |
| 11 | Record/Replay (v1) | done | RecordedTransport, divergence detector, `replay` CLI, exit 5 |

## Decisions and deviations

(Logged here as they happen.)
