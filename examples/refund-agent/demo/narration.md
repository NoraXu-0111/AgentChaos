# AgentChaos demo — narration (~60s, ~145 words)

Source of truth for timing/assets is `storyboard.json`; this is the human-readable script.

1. **(title)** Ship a change to your AI agent's prompt, model, or retrieval — and you often won't know what broke until it's in production.
2. **(dev loop)** AgentChaos is a reliability gate for your agent's CI. It runs your scenarios on every pull request — and it never scores answer quality.
3. **(regression)** Bump your retrieval from five chunks to twelve, and cost quietly jumps sixty-eight percent. AgentChaos catches the regression and fails the run.
4. **(cause)** Then it names the cause — correlating every metric delta with what actually changed in the trace, right down to the metadata.
5. **(proxy)** It also injects seeded chaos between your agent and its tools.
6. **(chaos)** A guaranteed 503 on get_order — and the agent degrades gracefully instead of crashing. That's a pass.
7. **(reproduce)** Same seed, same faults, every single run. Fully reproducible.
8. **(gate)** In CI it's one gate: clean changes pass; cost regressions and broken fallbacks get blocked by exit code — before they ship.
9. **(outro)** AgentChaos. Reliability testing for tool-using agents.
