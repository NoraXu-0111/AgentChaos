# 0004 — Defer framework adapters (LangGraph et al.) to v2

- Status: accepted
- Date: 2026-05-25

## Context

A common request will be "ship a LangGraph adapter" (and CrewAI, AutoGen,
OpenAI Agents SDK). Adapters are appealing — they make AgentChaos look native to
a framework and lower setup friction for that framework's users.

But adapters are a maintenance liability: each one tracks a fast-moving upstream
API, multiplies the test matrix, and risks coupling our core to a framework's
internals. Building them before the core wedge is validated spends scarce
attention on breadth instead of depth.

## Decision

No framework adapters in v0 or v1. Adapters arrive in **v2**, and even then
limited to **two** initially — LangGraph and OpenAI Agents SDK — with others
added only on demonstrated demand.

Until then, every agent is integrated the same way: a plain HTTP endpoint that
takes a message and returns a response. The transport infers fidelity from the
response shape; no per-framework code path exists in core.

## Consequences

- The core stays framework-agnostic and small; there is exactly one integration
  contract to document and support.
- We avoid chasing upstream breaking changes across N frameworks before we have
  the users to justify it.
- Adapters, when they come, are a thin scenario-construction convenience over
  the existing HTTP transport — not a fork of the execution path.
- Trade-off: framework users do a little more setup (stand up an HTTP endpoint)
  in v0/v1. Accepted; it also keeps the integration honest and testable.
- Revisit trigger: a framework maintainer reaching out, or repeated unsolicited
  adapter requests once v1 is in use.
