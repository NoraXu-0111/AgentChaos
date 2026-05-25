# Refund Agent — AgentChaos demo

A fake customer-support refund agent that demonstrates AgentChaos catching a real cost regression.

## Setup (under 60 seconds)

```bash
cd examples/refund-agent
# from the repo root, after `pip install -e ".[dev]"`
uvicorn server.main:app --host 127.0.0.1 --port 8080 &
SERVER_PID=$!
```

## 1. Verify the agent is up

```bash
agentchaos doctor scenarios/01-happy-path.yaml
```

You should see green checks for "Scenario parses" and "Endpoint reachable."

## 2. Run the happy path

```bash
agentchaos run scenarios/01-happy-path.yaml --out runs/baseline.jsonl
```

You should see `Verdict: PASS` and a trace at `runs/baseline.jsonl`.

## 3. Record a baseline with the rag-cost-regression scenario

```bash
agentchaos run scenarios/02-rag-cost-regression.yaml --out runs/baseline.jsonl
```

Same `PASS`. We now have a baseline measured against `rag_chunks=5`.

## 4. Catch the cost regression

The server's planner inflates token counts by `rag_chunks × 80`. Restart with a higher value:

```bash
kill $SERVER_PID
RAG_CHUNKS=12 uvicorn server.main:app --host 127.0.0.1 --port 8080 &
SERVER_PID=$!
```

Re-run against the same scenario, with the baseline:

```bash
agentchaos run scenarios/02-rag-cost-regression.yaml \
    --baseline runs/baseline.jsonl \
    --out runs/candidate.jsonl
```

You should see:

```text
Verdict: FAIL

Why:
  - [regression_budget] max_cost_regression_pct: cost regressed +<...>% (limit +20.0%)
  - [regression_budget] max_input_token_regression_pct: ...

Metrics:
  Metric                Baseline       Current        Δ   Status
  ----------------------------------------------------------------
  Cost                   $0.0006        $0.0019    +217%   FAIL
  Input tokens             1080            2360    +118%   FAIL
  ...

Possible contributors:
  - metadata.rag_chunks changed on model_call planner (turn 0): 5 -> 12  [correlates]
  - metadata.rag_chunks changed on model_call final_response (turn 1): 5 -> 12  [correlates]
  - input_tokens grew +118.5% (+1280 tokens)
  ...

Exit code: 2
```

Cleanup:

```bash
kill $SERVER_PID
```

## What this demonstrates

- **Cost regression detection** without ever scoring answer quality.
- **Structured "why cost changed"** — the report identifies that `rag_chunks` grew from 5 to 12 and correlates that with the input-token growth.
- **Trace artifacts** in `runs/` that are diff-friendly and replayable as baselines.
- **CI-shaped UX** — exit code 2 on regression, 0 on pass.
