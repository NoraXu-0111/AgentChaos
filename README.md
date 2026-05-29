# AgentChaos

**Open-source reliability testing for tool-using AI agents.** Record agent runs, profile cost, and catch operational regressions in CI — before they hit production.

> `0.1.0` — v0 wedge: detect a cost/latency/tool-call regression in CI. See [PROGRESS.md](PROGRESS.md) and the [roadmap](#roadmap).

## The problem

Tool-using agents fail in production in ways quality-focused eval tools don't catch:

- Cost silently doubles after a prompt or model change.
- A flaky tool returns 503 and the agent retries 12 times, racking up $4 in model calls.
- Retrieval returns 12 chunks instead of 5, blowing the planner's context budget.
- The "fallback when a tool fails" path was never tested, because tools never fail in dev.

Eval tools (LangSmith, Braintrust, DeepEval) score answer *quality*. Load tools (k6, Locust) don't understand the agent loop. AgentChaos covers the operational gap: **deliberate, reproducible regression detection for tool-using agents, runnable in CI.**

## Quickstart

```bash
pip install agentchaos
agentchaos init my-agent-tests
cd my-agent-tests
agentchaos doctor scenarios/example.yaml      # validate + ping your agent
agentchaos run scenarios/example.yaml          # record a baseline trace
# ... change your agent (prompt, model, retrieval) ...
agentchaos run scenarios/example.yaml --baseline runs/baseline.jsonl
```

A scenario is plain YAML: a conversation, the tools you expect, and operational budgets.

```yaml
id: refund-agent
agent:
  type: http
  endpoint: http://127.0.0.1:8080/chat
conversation:
  - user: "I want to return my order."
  - user: "My order number is 12345."
expect:
  must_call_tools: [get_order, create_return_label]
  final_response_contains: [return label]
budgets:
  max_cost_usd: 0.05
  max_cost_regression_pct: 20          # fail if cost grows >20% vs baseline
  max_input_token_regression_pct: 30
```

## What you get

Re-run after a change and AgentChaos diffs against the baseline, gates on your budgets, and tells you **why** cost moved — then exits non-zero so CI fails:

```
AgentChaos — refund-agent

Verdict: FAIL

Why:
  - [regression_budget] max_cost_regression_pct: cost regressed +68.2% (limit +20.0%)
  - [regression_budget] max_input_token_regression_pct: input_tokens regressed +90.8% (limit +30.0%)

Metrics:
  Metric                      Baseline       Current         Δ  Status
  --------------------------------------------------------------------
  Cost                         $0.0004       $0.0006    +68.2%  FAIL
  Input tokens                    1850          3530    +90.8%  FAIL
  Output tokens                    150           150     +0.0%  PASS
  LLM calls                          3             3     +0.0%  PASS
  Tool calls                         2             2     +0.0%  PASS

Tool sequence:
  baseline: get_order -> create_return_label
  current:  get_order -> create_return_label

Possible contributors:
  - input_tokens grew +90.8% (+1680 tokens)
  - per-model cost grew on gpt-4o-mini: $0.000368 → $0.000619 (+68.2%)
  - metadata.rag_chunks changed on model_call planner: 5 → 12  [correlates]

Exit code: 2
```

The cause detection is observation-first: it leads with deltas and lists *possible contributors* with confidence (`observed` / `correlates` / `computed`). Only a model swap claims a hard dollar contribution.

Try it now — the [refund-agent demo](examples/refund-agent/) reproduces the report above in under a minute.

## How it works

```
scenario.yaml → run → trace.jsonl → metrics → compare(baseline) → terminal verdict + exit code
```

Your agent is any HTTP endpoint that takes a message and returns a response. AgentChaos auto-detects one of three **fidelity tiers** from your response shape — full per-call cost attribution, aggregate usage, or message-only — and tells you which on the first run. No SDK, no instrumentation, no framework lock-in.

See the [HTTP integration contract](docs/http-contract.md) for the exact request/response shapes and fidelity tiers.

| Command | Purpose |
|---------|---------|
| `agentchaos init` | Scaffold a scenarios/ + runs/ folder |
| `agentchaos doctor` | Validate a scenario and probe the endpoint |
| `agentchaos run` | Execute a scenario, record a trace, optionally diff a baseline |
| `agentchaos compare` | Diff two existing traces — pure analysis, no agent calls |

Exit codes: `0` pass · `1` config error · `2` budget/expectation violation · `4` endpoint unreachable.

## What it is not

- Not a generic LLM eval platform. Use DeepEval, Braintrust, or LangSmith for answer-quality scoring.
- Not a prompt management tool. Use Langfuse or git.
- Not an observability dashboard. Use Phoenix or Datadog.
- Not a load testing framework. Use k6 or Locust.

AgentChaos does one thing: **catch operational failures and cost regressions in tool-using agents, in CI.**

## Roadmap

- **v0 (now)** — cost/regression profiling with baseline diff. ✅
- **v1** — chaos injection (tool failure/latency), loop & retry-storm detection, record/replay, OTel emission, GitHub Action.
- **v2** — framework adapters (LangGraph, OpenAI Agents SDK), MCP proxy + contract tests.

## License

Apache 2.0.
