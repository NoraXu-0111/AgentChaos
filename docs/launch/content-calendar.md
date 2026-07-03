# Content calendar — 2-week distribution push

Companion to `posts.md` (which holds the one-shot Show HN / Reddit / DM drafts).
This file: the day-by-day schedule + the X/LinkedIn drumbeat drafts.

**Channel rules (why this isn't "post everywhere daily"):**
- HN: ONE Show HN, ever, per project milestone. Reposts get flagged. Be online
  for the first hour to answer comments — that's what keeps it on the page.
- Reddit: one post per subreddit per release. Accounts that are >10% self-promo
  get banned. Comment helpfully in the sub for a few days before posting.
- X: high frequency is fine and expected. 3–5/week, build-in-public tone.
- Discord: one show-and-tell per server, then just be useful.

**Pre-flight (from posts.md — do not skip):**
- [ ] `pip install agentchaos-reliability` works on a clean machine
- [ ] Demo reproduces the FAIL report in <60s
- [ ] README wow-report matches current output
- [ ] Detectors branch merged (gives the launch a fresh hook)

---

## Week 1 — launch salvo

| Day | Channel | What |
|-----|---------|------|
| Mon | X | Post 1 (detector teaser) |
| Tue | **Show HN** (8–10am PT weekday) | Draft in posts.md — stay online 1–2h replying |
| Tue | X | Post 2 (link to the HN thread: "I'm on HN today") |
| Wed | r/LLMDevs | Reddit draft from posts.md, retitled for detectors |
| Thu | r/AI_Agents | Same story, reframed around "what breaks agents" |
| Thu | X | Launch thread (outline below — highest follower conversion) |
| Fri | X | Post 3 (demo video — the 62s mp4, native upload not link; pin it) |
| Fri | Discord (LangChain #show-and-tell, CrewAI equivalent) | 3-line blurb below |
| daily | X + Reddit + HN | Reply to every comment on your posts; 10+ value-add replies to bigger accounts posting about agent failures/costs |

## Week 2 — drumbeat + outreach

| Day | Channel | What |
|-----|---------|------|
| Mon | X | Post 4 (retry-storm story) |
| Tue | DMs | 5 design-partner messages (template in posts.md) |
| Wed | X | Post 5 (exit-code / CI philosophy) |
| Thu | DMs | 5 more DMs |
| Fri | X | Post 6 (meta: built with agents) + LinkedIn variant |
| daily | X | 15 min engagement: reply to people posting about agent failures/costs |

After week 2: 2–3 X posts/week, one Reddit/HN post only at the next real
milestone (chaos proxy = "break your agent on purpose in CI" — that's a
strong second Show HN in a few months, framed as a new capability).

---

## X mechanics (from x-twitter-growth — these change reach a lot)

- **Never put a link in the tweet body.** X down-ranks it. Post the tweet,
  then immediately reply to yourself with the link/install command.
- Under ~200 characters per tweet performs best. One idea per tweet.
- End with a question when natural — replies are the highest-weighted
  algorithm signal.
- Don't edit a tweet within 30 min of posting; don't post and go offline —
  stay around 15 min to reply.
- No hashtags. Screenshots/video native-uploaded, never linked.
- At <1K followers, **replies are the growth engine, not posts**: 10–20
  genuine value-add replies/day to accounts 2–10x your size (people posting
  about agent failures, LLM costs, eval tooling). Your reply is your content.
- Bio: first line = who you help + how ("Building AgentChaos — CI reliability
  gates for LLM agents. OSS."). Pin the demo-video tweet after Friday.

## X drumbeat drafts

Attach a terminal screenshot or one of the 8 images in
`examples/refund-agent/demo/assets/social/` where noted. `↳ reply:` = post
this as your own first reply, immediately after the tweet.

**Post 1 — detector teaser (attach detector-output screenshot)**
> My agent called the same tool 9 times with identical args.
>
> The eval passed. The answer looked fine. The bill did not.
>
> AgentChaos now catches loops, retry storms, and cost explosions in CI.
>
> What's the dumbest thing your agent has done without failing a test?

↳ reply: `pip install agentchaos-reliability` → github.com/NoraXu-0111/AgentChaos

**Post 2 — HN day**
> AgentChaos is on Hacker News right now.
>
> OSS CLI that fails your build when your agent quietly gets 2x more
> expensive — and names the cause.
>
> Link below. Toughest feedback wins.

↳ reply: <HN thread link>

**Post 3 — demo video (native upload of agentchaos-demo-720p.mp4)**
> 60 seconds: the change passes eval. AgentChaos fails the build.
>
> Input tokens +91%. Cause named: rag_chunks went 5 → 12.
>
> No SDK. Your agent is just an HTTP endpoint.

↳ reply: `pip install agentchaos-reliability` → repo link
(Pin this tweet after posting.)

**Post 4 — retry-storm story (attach retry-storm report screenshot)**
> A flaky tool + naive retries = 12 calls where there used to be 2.
>
> Your invoice notices before you do.
>
> So we built a retry-storm detector that fails CI instead.
>
> How do you cap retries in your agents today?

↳ reply: repo link + the 03-retry-storm scenario YAML

**Post 5 — CI philosophy (contrarian format, no link at all)**
> Unpopular opinion: "is the answer good?" is the wrong first question in
> agent testing.
>
> "Did this change double my cost?" is what actually breaks prod.
>
> Exit code 2 = budget violated. Your CI already knows what to do with that.

**Post 6 — meta / build-in-public (good LinkedIn crosspost)**
> I built an agent-reliability tool using a team of agents.
>
> A planner writes the spec. An executor TDDs it. A read-only evaluator
> checks exit criteria. 123 tests, zero phases skipped.
>
> The tool they built now tests other agents. Feels right.

↳ reply: repo link + one paragraph on the planner/executor/evaluator loop

**Launch thread — post Thursday of week 1 (threads convert followers best)**

Tweet 1 (hook): "I shipped a change that passed every eval. My token bill
went up 68%. Here's the bug class nobody's testing for: ↓"
2. The failure: answers looked right, cost doubled — quality evals can't see it
3. Why: eval tools score answers; load tools don't understand the agent loop
4. The trace: every tool call, retry, and token count recorded per run
5. The diff: baseline vs candidate → `rag_chunks 5 → 12 [correlates]` (screenshot)
6. The gate: budgets in YAML, exit code 2, CI fails the merge
7. Honesty tweet: what it deliberately does NOT do (no quality scoring,
   no prompt management, no dashboard) and what to use instead
8. CTA: "OSS, Apache-2.0, demo runs in 60s. Repo in reply. Follow along —
   next phase is chaos injection: breaking agents on purpose in CI."

↳ reply to tweet 1: repo link + restated hook

**Hook bank (A/B alternates — swap onto any post above)**
1. Number-led: `9 identical tool calls in 1 run.` / `My eval still gave it a pass.`
2. Contrarian: `Green evals mean your agent works.` / `Mine passed while costs rose 68%.`
3. Transformation: `I shipped agent bugs for 3 months.` / `Now CI catches them in 60 seconds.`
4. Authority steal: `LangSmith scores your answers.` / `I built the tool for your bill.`
5. Admission: `I doubled my token bill in 1 merge.` / `The diff looked completely safe.`
6. Future shock: `Agents are heading into CI in 2026.` / `I built the failing exit code.`

**Spares (use when something real happens):**
- First external issue/PR: screenshot it, say thanks publicly.
- Star milestones (10, 25, 50): one-liner + what's next.
- Anything surprising a detector catches in the wild → instant post.

---

## Discord blurb (LangChain / CrewAI / AutoGen show-and-tell)

> Built a small OSS CLI for the operational side of agent testing: it records a
> baseline trace of your agent (any HTTP endpoint, no SDK), then diffs cost /
> tokens / latency / tool calls on every change and fails CI on regressions —
> with the probable cause named (e.g. "rag_chunks 5 → 12 correlates with +91%
> input tokens"). Also detects loops and retry storms. Demo runs in <60s:
> https://github.com/NoraXu-0111/AgentChaos — feedback very welcome.

---

## Tracking

Log here after each post: date, channel, link, upvotes/likes, comments, stars
before → after. One line each. If a channel does 10x the others, shift the
calendar toward it.

| Date | Channel | Link | Result | Stars Δ |
|------|---------|------|--------|---------|
