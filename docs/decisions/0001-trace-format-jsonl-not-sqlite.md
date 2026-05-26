# 0001 — Trace format is JSONL, not SQLite

- Status: accepted
- Date: 2026-05-25

## Context

AgentChaos records every run as a trace: an ordered stream of events
(`run_meta`, `session_start`, `model_call`, `tool_call`, `session_end`,
`run_end`, …). This trace is the substrate everything else is built on —
metrics, baseline diffs, cause detection, and (in v1+) replay and OTel export.

We needed a storage format that is:

- diff-friendly and reviewable in a PR (baselines get committed to the repo);
- append-only and crash-safe during a run (a killed run should still yield a
  partially-readable trace);
- trivially streamable by future consumers (OTel exporter, HTML report);
- dependency-free and portable across macOS/Linux/Windows.

The obvious alternative was an embedded SQLite history store with a query layer.

## Decision

Traces are newline-delimited JSON (JSONL), one event per line, written with a
flush after each line. One file per run under `runs/`. Baselines are just trace
files that happen to be committed to git.

A SQLite history/comparison store is explicitly **out of scope for v0** (see
`13 - v0 Refined Plan.md`).

## Consequences

- Baselines diff cleanly in code review; a reviewer can see exactly which
  events changed between baseline and candidate.
- A run that crashes still leaves a valid prefix; the reader tolerates a
  truncated final line.
- No schema migrations, no DB file locking, no native dependency.
- `schema_version: "1"` on `run_meta` is locked and stays 1.x-compatible
  forever; new event kinds and optional fields are additive only.
- Trade-off: no indexed multi-run history queries. When that need is real
  (multi-run dashboards, trend analysis) it becomes a v3 concern and can be
  layered on top by ingesting JSONL — the JSONL stays the source of truth.
