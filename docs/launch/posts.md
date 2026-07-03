# Launch posts — v0 (0.1.0)

Drafts for the v0 launch. Tune voice before posting. The whole pitch rests on
one concrete story: **a silent cost regression caught in CI, with the cause
named.** Lead with that everywhere; don't bury it under feature lists.

Pre-flight before posting any of these:
- `pip install agentchaos-reliability` works on a clean machine.
- The demo reproduces the FAIL report in <60s.
- The repo README's wow-report matches current output.
- You have ~1 hour free to answer comments in the first wave (matters most on HN).

---

## Show HN

**Title:** `Show HN: AgentChaos – catch cost/latency regressions in tool-using agents in CI`

**Body:**

> I kept shipping changes to an LLM agent that still passed eval — the answers
> looked right — but quietly cost 2x more, or started calling a tool 9 times
> instead of 2. Quality eval tools (LangSmith, Braintrust, DeepEval) don't catch
> that. Load tools (k6, Locust) don't understand the agent loop.
>
> AgentChaos is a small OSS CLI for the operational gap: you write a scenario
> (a conversation + the tools you expect + budgets), record a baseline trace,
> then re-run after a change. It diffs against the baseline, gates on your
> budgets, and — the part I actually wanted — tells you *why* cost moved.
>
> Example: after a retrieval change, it failed CI with exit code 2 and:
>
>     Cost          $0.0004 → $0.0006   +68%   FAIL
>     Input tokens     1850 → 3530      +91%   FAIL
>     Possible contributors:
>       - metadata.rag_chunks changed on model_call planner: 5 → 12  [correlates]
>
> No SDK or framework lock-in — your agent is any HTTP endpoint. It auto-detects
> how much cost detail your responses expose (3 fidelity tiers) and tells you.
>
> Deliberately narrow: no answer-quality scoring, no prompt management, no
> dashboard. v1 adds chaos injection (break your agent on purpose in CI).
>
> Apache-2.0, Python 3.11+. Demo runs in under a minute:
> `pip install agentchaos-reliability` → repo has a refund-agent example.
>
> Repo: https://github.com/NoraXu-0111/AgentChaos
> Would love feedback, especially from people running tool-using agents in prod.

**First-comment seed (post yourself):** the honest scope boundary — what it
deliberately does *not* do, and which tool to use instead for each.

---

## r/LocalLLaMA / r/MachineLearning

**Title:** `I built an OSS tool to catch agent cost regressions in CI (not another eval framework)`

**Body:**

> Eval tools score whether the answer is good. They don't catch the agent that
> still answers correctly but now costs 2x, retries a flaky tool 12 times, or
> pulls 12 retrieval chunks instead of 5.
>
> AgentChaos profiles the operational side — cost, tokens, latency, tool calls,
> retries — and gates regressions vs a committed baseline, with a non-zero exit
> code so CI fails. The report leads with deltas and lists *possible
> contributors* (observed / correlates / computed), e.g. `rag_chunks: 5 → 12`
> correlating with an input-token jump.
>
> Your agent is just an HTTP endpoint — no SDK, no framework adapter. Apache-2.0,
> single `pip install`, demo runs in <60s.
>
> Repo + refund-agent demo: https://github.com/NoraXu-0111/AgentChaos
>
> Curious what operational failures others have hit that quality eval missed.

Note: read each subreddit's self-promotion rules; lead with the problem, not the
repo link. r/LocalLLaMA skews local-model; emphasize the no-vendor-lock-in,
runs-against-any-endpoint angle.

---

## X / short post

Superseded — polished X drafts (link-in-reply format, hooks, launch thread)
live in `content-calendar.md`. Original kept for reference:

> Your agent eval is green. Your bill doubled anyway.
>
> AgentChaos catches cost/latency/tool-call regressions in tool-using agents in
> CI — and tells you *why*. e.g. "rag_chunks 5 → 12 correlates with +91% input
> tokens." Exits non-zero so CI fails.
>
> OSS, any HTTP endpoint, no SDK. https://github.com/NoraXu-0111/AgentChaos
> (⚠ if reusing: move the link to a first reply — links in body kill reach)

---

## Design-partner outreach (3 targets)

Goal from the roadmap: 3 teams running it on their *own* agents.

Template (DM / email):

> Hi <name> — saw you're building <agent product>. I made a small OSS CLI that
> catches cost/latency/tool-call regressions in tool-using agents in CI — points
> at the likely cause, not just "cost went up." No SDK; it runs against any HTTP
> endpoint, so trying it on your agent is ~15 min. Would a quick look be useful?
> If you hit a real bug I'll fix it before the public launch.

Pick targets where: (1) the agent is reachable over HTTP, (2) they've felt a
surprise bill or a runaway-retry incident, (3) they're active enough to give
real feedback. Track responses here as you go.
