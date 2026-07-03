# AgentChaos — social content pack (LinkedIn ×4 + X ×4)

Images live in `assets/social/`. Each post below names its paired image.
LinkedIn images are premium/clean **portrait 4:5**; X images are bold/edgy
**landscape 16:9** — different visual pitch per platform, as requested.
LinkedIn copy follows the post-formatter frameworks; X copy is native/punchy.

Repo link used: `github.com/NoraXu-0111/AgentChaos` — swap if you use a different handle.

---

## LinkedIn

### LI-1 · image `assets/social/li_1.png` · framework: PAS
```
Your AI agent passed every quality eval.

It still broke in production.

Quality evals score answers.

They never score what it costs to get them.

So the failures hide where you do not look:

1. Cost doubles after a prompt tweak.

2. A flaky tool 503s and it retries twelve times.

3. The fallback path was never once tested.

None of that shows up in an answer score.

All of it shows up in your bill.

AgentChaos is a reliability gate for agent CI.

It profiles cost, tokens, and tool calls per run.

It fails the build when they regress.

It never grades answer quality.

Catch the regression in the pull request.

Not in the incident channel.

If this helped, repost ♻️
```

### LI-2 · image `assets/social/li_2.png` · framework: BAB
```
Retrieval returned 5 chunks. Then 12.

Your cost just rose 68 percent. Silently.

Before:

You ship the change.

Cost creeps up for three weeks.

You find out when finance asks.

After:

The pull request fails on the spot.

The report names the cause for you.

rag_chunks: 5 to 12. Correlates.

Cost: plus 68 percent. Blocked.

The bridge is one baseline file.

AgentChaos diffs every run against it.

Cost, latency, tokens, and tool calls.

Regress past budget and the build stops.

Find it in the diff, not the dashboard.

Repost this if it would help your team ♻️
```

### LI-3 · image `assets/social/li_3.png` · framework: STAR
```
A tool returned 503 at 3am.

Did your agent degrade, or melt down?

Most teams never find out.

Tools never fail in dev, so the fallback never runs.

Until the one night it has to.

AgentChaos injects the fault for you.

A seeded 503 between the agent and its tools.

The agent must recover, or the run fails.

Same seed, same faults, every run.

So a green check means it truly degrades well.

1. Inject the fault.

2. Prove the fallback.

3. Replay it in CI forever.

Reliability you can reproduce.

Not reliability you hope for.

If this helped, repost ♻️
```

### LI-4 · image `assets/social/li_4.png` · framework: AIDA
```
One CI step. Three ways to block a bad merge.

Your agent does not need a new dashboard.

It needs a gate.

AgentChaos runs your scenarios on every PR.

Then it answers with one exit code:

1. Clean change. Exit 0. Ship it.

2. Cost regression. Exit 2. Blocked.

3. Broken fallback under chaos. Blocked.

Green means safe to merge.

Red tells you exactly why it is not.

It is open source and drops into CI.

It guards how the agent behaves, not what it says.

Put the gate in front of production.

Before production puts it in front of you.

Star it. Try it. Break it on purpose.

Repost this if your team ships agents ♻️
```

---

## X / Twitter

### X-1 · image `assets/social/x_1.png`
```
Your AI agent passed every eval and still doubled its cost in prod.

Quality evals score answers. They never score what the answer costs.

AgentChaos is a reliability gate for agent CI: profile cost, catch regressions, block the merge.

Open source 👇
github.com/NoraXu-0111/AgentChaos
```

### X-2 · image `assets/social/x_2.png`
```
Tools never fail in dev.

So your agent's fallback path has never actually run.

AgentChaos injects seeded, reproducible 503s between your agent and its tools, and fails CI if it doesn't degrade gracefully.

Chaos engineering, for AI agents.
github.com/NoraXu-0111/AgentChaos
```

### X-3 · image `assets/social/x_3.png`
```
Break your AI agent on purpose.

Inject faults. Spike the cost. Watch the fallback.

Then gate it all in CI so the broken version never ships.

AgentChaos — open source 👇
github.com/NoraXu-0111/AgentChaos
```

### X-4 · image `assets/social/x_4.png`
```
Meet the chaos monkey for AI agents 🐒

It 503s your tools, inflates your tokens, and breaks your fallback — on purpose, with a fixed seed — so CI catches it before prod does.

pip install agentchaos-reliability
github.com/NoraXu-0111/AgentChaos
```

---

### Posting notes
- X images are 16:9 (fills the in-feed card). LinkedIn images are 4:5 (max feed height).
- For a stronger LinkedIn play, post LI-1..LI-4 as single-image posts over a few days,
  OR reuse the 8-slide carousel in `assets/linkedin/` for one anchor post.
- X likes fewer hashtags; the posts above intentionally use none. Add 1–2 if you want
  (#AIagents #LLMOps).
