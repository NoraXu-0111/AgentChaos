# 0002 — No LLM-as-judge / answer-quality scoring in core

- Status: accepted
- Date: 2026-05-25

## Context

The crowded part of the market — LangSmith, Braintrust, DeepEval — scores
*answer quality*: is the response correct, helpful, faithful, on-topic? Much of
that scoring uses an LLM as a judge.

AgentChaos targets a different, under-served gap: **operational** reliability of
tool-using agents — cost, latency, tool-call counts, retries, loops — even when
the answer still looks right. The wedge is "did my agent get more expensive,
slower, or operationally riskier?" not "is the answer good?"

The temptation to add a quality score is strong: users ask for it, and it would
make us look feature-comparable to the eval tools.

## Decision

The core product does **not** score answer quality and does **not** embed an
LLM-as-judge. Task sanity in v0 is limited to cheap, deterministic checks under
`expect`: `must_call_tools`, `must_not_call_tools`, `final_response_contains`,
`final_response_not_contains`. These are string/set assertions, not judgments.

This is one of the three standing "no" rules in `CONTRIBUTING.md` (no quality
scoring, no prompt management, no dataset management).

## Consequences

- Verdicts are deterministic and reproducible: no model in the evaluation path,
  no flaky judge, no judge-model cost, no prompt to tune.
- Positioning stays sharp — "use DeepEval/Braintrust/LangSmith for answer
  quality" is a feature, not an apology. It keeps us out of a fight we don't
  need to win.
- A custom-evaluator marketplace is a v3-only maybe, and only if it can stay out
  of eval-quality territory.
- Trade-off: users who want one tool for both quality and ops will need two
  tools. Accepted — being excellent at the operational gap beats being mediocre
  at everything.
