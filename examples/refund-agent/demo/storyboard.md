# AgentChaos demo — storyboard

Scene durations are driven by each line's voiceover length (per-scene MP3 measured
by `build_video.py`), so line ↔ scene stay in sync. Target total ≈ 60s.

| # | Scene | Asset | Caption (burned-in) | Narration beat |
|---|-------|-------|---------------------|----------------|
| 1 | Title | `broll_title.mp4` (fal.ai; ffmpeg card fallback) | AgentChaos | The problem: changes break agents silently |
| 2 | Dev loop | `diagram_devloop.png` | A reliability gate in your CI | What it is + where it fits |
| 3 | Cost regression | `shot_A2_regression.png` | Cost regression, caught | rag_chunks 5→12, +68%, exit 2 |
| 4 | Root cause | `diagram_cause.png` | Names the root cause | Correlates deltas to trace metadata |
| 5 | Chaos proxy | `diagram_proxy.png` | Seeded chaos proxy | Fault injection agent→proxy→tools |
| 6 | Graceful fallback | `shot_B1_chaos.png` | Graceful degradation = PASS | 503 on get_order → fallback, PASS |
| 7 | Reproducible | `shot_B2_reproduce.png` | Same seed, same faults | Deterministic across runs |
| 8 | CI gate | `shot_C_gate.png` | One gate, distinct exit codes | exit 0 / 2 / 4 block the merge |
| 9 | Outro | `broll_outro.mp4` (fal.ai; ffmpeg card fallback) | AgentChaos | Tagline |

## Look & feel
- Dark terminal theme (`#12131c`), monospace caps, accent: cyan title / green pass / red fail / amber metrics.
- Stills get a slow Ken-Burns zoom; crossfades between scenes; captions burned bottom-left.
- Single concatenated voiceover track over the whole timeline.

## Exit-code legend (used in narration/diagrams)
`0` pass · `2` budget/cost regression · `3` chaos fallback assertion · `4` agent crashed under chaos.
(The demo's broken agent crashes → exit 4; exit 3 is the same gate for a bad-but-non-crashing fallback.)
