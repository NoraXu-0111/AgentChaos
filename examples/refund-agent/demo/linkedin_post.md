# LinkedIn post — AgentChaos

**Images:** upload `assets/linkedin/slide_1_hero.png … slide_8_cta.png` in order as a
carousel (LinkedIn → "Add a document" works too if you'd rather post them as a PDF deck;
all slides are 1080×1350, 4:5).

Regenerate anytime: `node make_linkedin.mjs` (reads the existing diagram/shot assets).

---

## Caption (option A — problem-first)

I kept shipping agent changes that looked fine in dev and broke in prod.

A prompt tweak quietly doubled cost. A flaky tool 503'd and the agent retried 12 times. Retrieval returned 12 chunks instead of 5 and blew the context budget. None of it showed up in quality evals — because evals score answers, not operations.

So I built **AgentChaos**: open-source reliability testing for tool-using AI agents.

→ Profile cost, latency, tokens, and tool calls on every run
→ Catch regressions in CI and name the root cause (not just the delta)
→ Inject seeded, reproducible chaos (503s, latency) and prove your fallback path actually works
→ One drop-in gate that blocks the merge by exit code — and never scores answer quality

It caught a +68% cost regression and a broken fallback in the demo refund agent before either could ship.

`pip install agentchaos-reliability`
github.com/NoraXu-0111/AgentChaos

Would love feedback — and if it's useful, a ⭐ helps.

#AIagents #LLM #MLOps #opensource #reliability #AIengineering

---

## Caption (option B — short)

Your AI agent passed every quality eval and still doubled its cost in prod.

**AgentChaos** is open-source reliability testing for tool-using agents: profile cost, catch regressions in CI, inject seeded chaos, and gate every PR by exit code — without ever scoring answer quality.

`pip install agentchaos-reliability` · github.com/NoraXu-0111/AgentChaos

#AIagents #LLM #MLOps #opensource
