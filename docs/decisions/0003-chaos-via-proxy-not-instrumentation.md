# 0003 — Chaos injection via proxy, not framework instrumentation

- Status: accepted (forward-looking; chaos ships in v1)
- Date: 2026-05-25

## Context

The v1 theme is "I can break my agent on purpose in CI" — inject tool failures,
latency, and bad status codes to test the agent's fallback paths. There are two
ways to inject faults:

1. **Instrumentation**: hook into each agent framework (LangGraph, OpenAI Agents
   SDK, CrewAI, …) and wrap tool calls from the inside.
2. **Proxy**: sit between the agent and its tools at the HTTP boundary and
   manipulate requests/responses (failure_rate, latency_ms, status_code).

v0 already speaks to agents over plain HTTP with no SDK and no framework
coupling — the transport infers fidelity from the response shape. We want chaos
to preserve that property.

## Decision

Chaos is injected at the **transport/proxy boundary**, not via per-framework
instrumentation. The chaos proxy sits between the transport and the real HTTP
endpoint and injects `failure_rate`, `latency_ms`, and `status_code`,
recording `chaos_injected` events into the same trace.

Per the roadmap, chaos is **not built until v0 has traction (~50+ users)** —
this ADR records the *approach* so the decision isn't re-litigated, not a
commitment to build it now.

## Consequences

- Chaos works for any agent reachable over HTTP, with zero framework adapters —
  consistent with the v0 "any HTTP endpoint" contract.
- One injection mechanism to build, test, and document instead of one per
  framework.
- The proxy is also what makes recorded tool responses reusable, so it must land
  **before** record/replay (v1 sequencing: chaos proxy → loop/retry detectors →
  replay).
- Framework adapters (v2) become a thin convenience layer for constructing
  scenarios, not a prerequisite for chaos.
- Trade-off: faults are injected at the network boundary, so in-process tool
  calls that never cross HTTP can't be perturbed by the proxy. Acceptable: the
  target users expose tools over HTTP/MCP.
