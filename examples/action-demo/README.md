# AgentChaos GitHub Action demo

The composite action at the repo root (`action.yml`) wraps `agentchaos run --baseline`:
it runs one scenario, writes a markdown + JUnit report, upserts a PR comment with the
cost diff + verdict, and fails the job according to `fail-on`.

## Usage

```yaml
permissions:
  contents: read
  pull-requests: write   # required for the PR comment

steps:
  - uses: actions/checkout@v4
  - uses: NoraXu-0111/AgentChaos@v1
    with:
      scenario: scenarios/refund.yaml
      baseline: runs/baseline.jsonl        # omit on the first run
```

Key inputs (all optional except `scenario`):

| Input | Default | Purpose |
|-------|---------|---------|
| `scenario` | — | Scenario YAML path (required) |
| `baseline` | `""` | Baseline trace to diff against; empty = no baseline |
| `fail-on` | `"1,2,3,4,5"` | Exit codes that fail the job; `""` = report-only |
| `comment` | `"true"` | Post/update the PR comment |
| `working-directory` | `"."` | Directory paths resolve relative to |
| `package` | `agentchaos-reliability` | pip install target (use `-e .` for a checkout) |
| `seed` | `""` | Deterministic seed for `agentchaos run --seed` |

Outputs: `exit-code`, `outcome` (`pass`/`fail`), `md-path`, `junit-path`, `trace-path`.

One scenario per invocation — test several scenarios with a job `matrix`; the comment
marker embeds the scenario name, so each matrix leg upserts its own comment.

The live demo is [`.github/workflows/agentchaos-demo.yml`](../../.github/workflows/agentchaos-demo.yml):
on PRs touching `examples/**` it records a baseline at `RAG_CHUNKS=5`, restarts the
refund agent at `RAG_CHUNKS=12`, and the action posts the FAIL comment with the cost diff.

## Reproduce locally

The action's core is just the CLI — reproduce the demo workflow end to end:

```bash
# from the repo root
python -m pip install -e .
cd examples/refund-agent

# 0. Start the tools service — the agent makes real HTTP tool calls to :8090.
uvicorn tools.main:app --host 127.0.0.1 --port 8090 &

# 1. Start the agent with the baseline retrieval config and record a baseline.
RAG_CHUNKS=5 uvicorn server.main:app --host 127.0.0.1 --port 8080 &
agentchaos doctor scenarios/02-rag-cost-regression.yaml
agentchaos run scenarios/02-rag-cost-regression.yaml --out runs/baseline-ci.jsonl
kill %2 && wait %2 2>/dev/null   # let port 8080 free up before restarting

# 2. Restart the agent with the regressed config and run the gate command the action runs.
RAG_CHUNKS=12 uvicorn server.main:app --host 127.0.0.1 --port 8080 &
agentchaos run scenarios/02-rag-cost-regression.yaml \
  --baseline runs/baseline-ci.jsonl \
  --out agentchaos-run.jsonl \
  --md-out agentchaos-report.md \
  --junit-out agentchaos-junit.xml
kill %2 %1

# 3. Inspect what the action would post: the markdown report is the PR comment body.
cat agentchaos-report.md      # first line is the upsert marker; Cost row shows the + delta
cat agentchaos-junit.xml      # 6 testcases, check_regression_budget carries the failure
```

The `agentchaos run` exits `2` (budget/expectation violation); in CI the action's
`fail-on` input decides whether that fails the job.
