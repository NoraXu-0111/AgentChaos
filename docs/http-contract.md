# HTTP integration contract

AgentChaos talks to the agent under test through one HTTP endpoint. There is no
SDK, framework adapter, or in-process instrumentation in v0.

## Request

For each user turn in the scenario, AgentChaos sends:

```http
POST /chat
Content-Type: application/json
```

```json
{
  "session_id": "s-1234abcd",
  "message": "I want to return my order."
}
```

The same `session_id` is reused for every turn in one scenario run. Your agent
can use it to keep conversation state.

## Response tiers

AgentChaos auto-detects fidelity from the response shape.

| Tier | Required response shape | What AgentChaos can measure |
| ---- | ----------------------- | --------------------------- |
| `full` | `message` plus `events[]` | Per-call model/tool details, cost, tokens, tool sequence, causes |
| `aggregate` | `message` plus `usage` and/or `tool_calls[]` | Run-level cost/tokens and tool counts |
| `message_only` | `message` only | Final text, latency, HTTP errors |

Higher fidelity gives better reports. A v0 launch-ready integration should aim
for `full`.

## Full-fidelity response

```json
{
  "session_id": "s-1234abcd",
  "message": "Found order #12345. Your return label is on its way.",
  "agent": {
    "name": "refund-agent",
    "version": "0.1.0",
    "model": "gpt-4o-mini"
  },
  "events": [
    {
      "type": "model_call",
      "name": "planner",
      "model": "gpt-4o-mini",
      "input_tokens": 600,
      "output_tokens": 40,
      "cost_usd": 0.000114,
      "latency_ms": 220,
      "metadata": {
        "rag_chunks": 5,
        "prompt_version": "refund-v3"
      }
    },
    {
      "type": "tool_call",
      "name": "get_order",
      "args": {
        "order_id": "12345"
      },
      "latency_ms": 60,
      "result_summary": "ok",
      "retries": 0
    }
  ],
  "usage": {
    "input_tokens": 600,
    "output_tokens": 40,
    "cost_usd": 0.000114
  }
}
```

For `full` responses, AgentChaos computes cost and token totals from
`events[].type == "model_call"`. The top-level `usage` object is optional and is
recorded on the agent turn, but it is not double-counted.

### `model_call` fields

| Field | Required | Notes |
| ----- | -------- | ----- |
| `type` | yes | Must be `"model_call"` |
| `model` | yes | Model name used for by-model cost breakdowns |
| `name` | no | Logical step name, such as `planner` or `final_response` |
| `input_tokens` | no | Integer token count |
| `output_tokens` | no | Integer token count |
| `cost_usd` | no | Float cost in US dollars |
| `latency_ms` | no | Integer latency |
| `ttft_ms` | no | Integer time-to-first-token |
| `stop_reason` | no | Provider stop reason |
| `metadata` | no | Small scalar metadata for cause hints |

Metadata is where AgentChaos can explain regressions. For example, if
`metadata.rag_chunks` changes from `5` to `12` and input tokens grow, the report
can surface that correlation.

### `tool_call` fields

| Field | Required | Notes |
| ----- | -------- | ----- |
| `type` | yes | Must be `"tool_call"` |
| `name` | yes | Tool name used by `must_call_tools` checks |
| `args` | no | JSON object; AgentChaos records a stable args hash |
| `latency_ms` | no | Integer latency |
| `result_summary` | no | One of `ok`, `error`, `malformed` |
| `result_size_bytes` | no | Integer result size |
| `error` | no | Error string, if the tool failed |
| `retries` | no | Integer retry count for this logical call |
| `metadata` | no | Small scalar metadata |

## Aggregate response

Use this if your agent cannot expose per-call events yet.

```json
{
  "message": "Your return label is on its way.",
  "usage": {
    "input_tokens": 1200,
    "output_tokens": 80,
    "cost_usd": 0.000228
  },
  "tool_calls": [
    {
      "name": "get_order",
      "args": {
        "order_id": "12345"
      },
      "result_summary": "ok",
      "retries": 0
    }
  ]
}
```

Aggregate responses can enforce cost/token/tool budgets, but cause detection is
less precise because model calls and tool calls are not tied to individual
agent steps.

## Message-only response

```json
{
  "message": "Your return label is on its way."
}
```

Message-only responses are valid, but cost and token metrics are unknown. This
tier is useful for checking endpoint reachability and simple final-response
expectations.

## Error handling

AgentChaos records transport errors instead of raising them as Python
exceptions:

- HTTP status `>= 400` becomes a transport failure.
- Timeout becomes `timeout`.
- Non-JSON response becomes `non_json_response`.
- A JSON response that is not an object becomes `response_not_object`.

Transport failures exit with code `4`.

## Quick probe

With an agent running on `127.0.0.1:8080`:

```bash
curl -sS -X POST http://127.0.0.1:8080/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"probe","message":"ping"}'
```

Then validate the scenario:

```bash
agentchaos doctor scenarios/example.yaml
```

Use the same host in both commands. If your server binds to `127.0.0.1`, prefer
`http://127.0.0.1:...` in the scenario rather than `localhost`; on some
machines `localhost` may resolve to a different local service.
