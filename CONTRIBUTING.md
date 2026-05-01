# Contributing to AgentChaos

Thanks for your interest. AgentChaos is a deliberately narrow tool — it does one thing well rather than many things adequately.

## The three "no"s

These keep AgentChaos from drifting into eval-tool territory. PRs proposing them will be redirected:

1. **No LLM-as-judge for answer quality in core.** Use DeepEval, Braintrust, or LangSmith.
2. **No prompt management.** Use Langfuse or git.
3. **No dataset management.** Use Langfuse or DeepEval datasets.

## What's in scope

- Operational metrics: cost, tokens, latency, tool calls, retries, errors.
- Regression detection between baseline and candidate runs.
- Lightweight task assertions: `must_call_tools`, `final_response_contains`.
- Trace recording in JSONL with stable schema.
- CI integration via exit codes.

## Development

```bash
git clone https://github.com/agentchaos/agentchaos
cd agentchaos
uv venv -p 3.11 .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
pytest -q
ruff check .
mypy agentchaos
```

## Style

- 100-character lines. `ruff format`.
- Type hints on public APIs. Pydantic for data models.
- Tests alongside code. Aim for ≥85% coverage.
- One feature per PR. Small PRs > big PRs.
