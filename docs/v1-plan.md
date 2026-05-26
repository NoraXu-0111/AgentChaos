# v1 Plan — "Reliability gate" (chaos)

> Living doc. v1 theme: **"I can break my agent on purpose in CI."**
> Source of truth for scope: `09 - Roadmap.md` and the "After v0 — what unlocks"
> section of `13 - v0 Refined Plan.md` in the design vault.

## Gating rule (read first)

Per roadmap principle #2: **do not start building chaos until v0 has ~50+ users.**
v1 is a forward plan that activates on traction, not a queue to start the day
after v0 ships. Building the most complex subsystem before the v0 wedge is
validated would invert the roadmap's own sequencing.

**Activation signal:** ~50+ users on v0 (proxy for "the wedge landed"), or a
design partner explicitly asking for fault injection.

## Why this is cheap to build later

The v0 trace → metrics → diff → verdict pipeline was designed as the substrate.
Each v1 feature is an extension, not a rewrite:

- **Chaos** = inject between transport and HTTP; add `chaos_injected` events.
- **Replay** = swap `HTTPTransport` for a `RecordedTransport` reading a trace.
- **GitHub Action** = wrap `agentchaos run --baseline`; post the terminal report
  as a PR comment.
- **OTel** = a streaming consumer of the trace JSONL → OTLP exporter.
- **HTML report** = a jinja2 template fed the same `Verdict + Diff + Causes`.

Exit codes `3` (chaos detected) and `5` (replay divergence) are already reserved
in the v0 spec.

## Workflow (each phase)

Same loop used for v0 phases 0–8: **planner → executor → evaluator.**
- `planner` reads the design docs + this plan, emits exact file paths,
  signatures, ≥3 unit tests per function, edge cases, and verbatim exit criteria.
- `executor` implements TDD, iterates until green, reports files + test status.
- `evaluator` (read-only) runs tests/coverage and reports pass/fail per criterion.

## Phases (continue numbering from v0's 0–8)

### Phase 9 — Chaos proxy
Transport-level fault injection. A proxy sits between the transport and the real
HTTP endpoint (ADR-0003: chaos via proxy, not framework instrumentation).
- Inject `failure_rate`, `latency_ms`, `status_code`.
- Emit `chaos_injected` trace events.
- New scenario block (`chaos:`) + deterministic seeding for reproducibility.
- Exit code `3` when chaos-related expectations fail.
- **Exit criteria:** a scenario can declare a 50% failure_rate on tool X; the
  run records `chaos_injected` events and the agent's fallback path is observable
  in the trace; reproducible across runs given a fixed seed.

### Phase 10 — Detectors
Pure functions over existing trace events (no new transport work).
- **Loop detector:** same `args_hash` for a tool ≥N times in a sliding window.
- **Retry-storm detector:** retry count spikes beyond a threshold.
- **Cost-explosion classifier:** ties a cost spike to a probable driver.
- Surface in the terminal report; gate via budgets (reuses exit code `2`).
- **Exit criteria:** the retry-storm demo scenario fires the loop detector; each
  detector is a unit-tested pure function with ≥3 fixture cases.

### Phase 11 — Record / replay
- `RecordedTransport` replays tool/model responses from a prior trace.
- `replay_divergence` detection: candidate behavior diverges from recording.
- Exit code `5` on divergence.
- **Exit criteria:** a recorded trace replays deterministically with zero live
  HTTP; an intentional agent change produces a reported divergence + exit 5.

### Phase 12 — OTel emitter
- GenAI semantic-conventions emitter; `agentchaos export-otel <trace>`.
- Streaming consumer of trace JSONL → OTLP exporter (no core coupling).
- **Exit criteria:** a trace exports to an OTLP collector; spans carry GenAI
  semconv attributes (model, tokens, cost); verified against a local collector.

### Phase 13 — GitHub Action + CI polish
- `agentchaos/run-action@v1` wrapping `run --baseline`.
- PR markdown comment with the cost diff + verdict.
- JUnit XML output for native CI test reporting.
- **Exit criteria:** a sample repo's PR shows the AgentChaos comment with the
  cost diff; JUnit XML validates against the schema.

### Phase 14 — HTML report
- Single-file jinja2 report fed the same `Verdict + Diff + Causes` objects.
- **Exit criteria:** `agentchaos run --html out.html` produces a self-contained
  file rendering the verdict, metric diff, tool sequence, and contributors.

### Phase 15 — v1 launch
- Version `0.2.0`.
- Chaos demo video (retry-storm scenario actually fires the loop detector).
- One-line GH Action snippet posting a PR comment with the cost diff.
- **Success metric (roadmap):** 100 GitHub stars, 5 production users, 1 framework
  maintainer reaches out.

## Out of scope for v1 (still)

Framework adapters, MCP, production trace import, concurrency, hosted dashboard,
distributed runners. Those are v2/v3 (see `09 - Roadmap.md`).

## Sequencing note

Chaos proxy (Phase 9) lands **before** replay (Phase 11) on purpose: the proxy
is what makes recorded tool responses reusable. Don't reorder.
