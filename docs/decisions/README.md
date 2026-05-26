# Architecture Decision Records

Settled scope and design decisions, ADR-style. These exist to stop future
contributors (and future us) from re-litigating questions that are already
decided. A PR that proposes reversing one of these should update the relevant
ADR with new context, not quietly ignore it.

- [0001 — Trace format is JSONL, not SQLite](0001-trace-format-jsonl-not-sqlite.md)
- [0002 — No LLM-as-judge / answer-quality scoring in core](0002-no-llm-as-judge-in-core.md)
- [0003 — Chaos injection via proxy, not framework instrumentation](0003-chaos-via-proxy-not-instrumentation.md)
- [0004 — Defer framework adapters (LangGraph et al.) to v2](0004-defer-langgraph-adapter-to-v2.md)
