# AgentChaos

**Open-source reliability testing for tool-using AI agents.** Record agent runs, profile cost, detect regressions in CI before production.

> Status: pre-alpha (`0.1.0.dev0`). v0 in active development. See [PROGRESS.md](PROGRESS.md).

## Why

Tool-using agents fail in production in ways quality-focused eval tools don't catch:
- Cost silently doubles after a prompt or model change.
- A flaky tool returns 503 and the agent retries 12 times, racks up $4 in model calls.
- Retrieval returns 12 chunks instead of 5, blowing the planner's context budget.
- The "fallback when tool fails" path was never tested because tools never fail in dev.

Existing eval tools (LangSmith, Braintrust, DeepEval) score answer quality. Existing load tools (k6, Locust) don't understand the agent loop. AgentChaos covers the operational gap: **deliberate, reproducible regression detection for tool-using agents, runnable in CI**.

## Quickstart

```bash
pip install agentchaos
agentchaos init my-agent-tests
cd my-agent-tests
agentchaos doctor scenarios/example.yaml
agentchaos run scenarios/example.yaml
```

## What it is

- CLI-first, OSS Apache 2.0.
- Python 3.11+.
- Single binary install.
- Plays nicely with Langfuse, Phoenix, Datadog (OpenTelemetry GenAI emission planned for v1).

## What it is not

- Not a generic LLM eval platform. Use DeepEval, Braintrust, or LangSmith for answer-quality scoring.
- Not a prompt management tool. Use Langfuse or git.
- Not an observability dashboard. Use Phoenix or Datadog.
- Not a load testing framework. Use k6 or Locust.

AgentChaos focuses on one thing: **catching operational failures and cost regressions in tool-using agents, in CI.**

## License

Apache 2.0.
