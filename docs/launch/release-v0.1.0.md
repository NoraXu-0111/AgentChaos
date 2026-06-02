# Release notes draft — v0.1.0

Use after the checks in [the v0 publish checklist](../release-checklist.md)
pass and PyPI publish succeeds. Commands:

```bash
git checkout main && git pull
git tag -a v0.1.0 -m "v0.1.0 — first public release"
git push origin v0.1.0
gh release create v0.1.0 --title "v0.1.0 — first public release" --notes-file docs/launch/release-v0.1.0.md
```

---

## v0.1.0 — first public release

**AgentChaos catches cost, latency, and tool-call regressions in tool-using AI
agents — in CI, before they hit production.**

Write a scenario (a conversation + the tools you expect + budgets), record a
baseline, then re-run after a change. AgentChaos diffs against the baseline,
gates on your budgets, and tells you *why* cost moved — then exits non-zero so
CI fails.

```
Verdict: FAIL
  Cost          $0.0004 → $0.0006   +68%   FAIL
  Input tokens     1850 → 3530      +91%   FAIL
Possible contributors:
  - metadata.rag_chunks changed on model_call planner: 5 → 12  [correlates]
Exit code: 2
```

### What's in v0
- Four commands: `init`, `doctor`, `run`, `compare`.
- Scenario YAML: conversation + `expect` (task sanity) + `budgets` (absolute and
  regression-vs-baseline).
- JSONL trace format (`schema_version: "1"`, stable).
- Cost/token/latency/tool-call/retry metrics with baseline diff.
- Observation-first cause detection (observed / correlates / computed).
- Three fidelity tiers auto-detected from your agent's response shape.
- Your agent is any HTTP endpoint — no SDK, no framework lock-in.

### Install
```bash
pip install agentchaos-reliability
```
Python 3.11+. macOS, Linux, Windows (CI-tested on all three).

### Try it
The [refund-agent demo](https://github.com/NoraXu-0111/AgentChaos/tree/main/examples/refund-agent)
reproduces the report above in under a minute.

### Deliberately not included
No answer-quality scoring, no prompt management, no dashboard. Those are other
tools' jobs (see the README's "What it is not"). v1 adds chaos injection —
breaking your agent on purpose in CI.

### License
Apache-2.0.
