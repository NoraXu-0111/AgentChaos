# AgentChaos demo video

A ~60s explainer showing what AgentChaos does and where it fits in the agent dev
loop. Everything here is self-contained under `examples/refund-agent/demo/` and
generated from the real CLI / library — no product code is modified.

**Output:** `agentchaos-demo.mp4` (1920×1080, H.264 + AAC, ~62s) and
`agentchaos-demo-720p.mp4` (web copy).

## The three scenarios
- **A — cost regression (CI):** `rag_chunks` 5→12 inflates input tokens; the run
  fails with **exit 2** and names the cause (`rag_chunks 5 → 12 [correlates]`).
- **B — seeded chaos:** a guaranteed 503 on `get_order`; the agent takes its
  observable fallback and **passes (exit 0)**, reproducibly by seed.
- **C — the CI gate:** the same agent through three checks → distinct exit codes
  block the merge: `0` clean · `2` cost regression · `4` agent crashed under chaos.

> Exit-code legend: `0` pass · `2` budget/regression · `3` chaos fallback assertion
> · `4` transport/agent crash. The demo's broken agent crashes under the injected
> 503, so it exits `4`; `3` is the same gate for a non-crashing bad fallback.
> (Note: end-to-end via HTTP, a surfaced agent error becomes a session error and
> resolves to exit 4 — exit 3 is reachable in the verdict layer / unit tests.)

## Prerequisites
- `uv` (Python 3.11), `ffmpeg`/`ffprobe`, Node ≥18 (`npm i` installs `sharp`).
- Secrets in the gitignored `../../../.demo.env`:
  `FAL_KEY` (fal.ai b-roll) and `ELEVENLABS_API_KEY` (voiceover). Both have local
  fallbacks (ffmpeg title cards / macOS `say`), so the build runs without keys.

## Regenerate end-to-end
```bash
ROOT=/Users/noraxu/workspace/agentchaos
cd "$ROOT/examples/refund-agent"

# 1. Capture scenarios A (cross-process CLI) and the CI gate.
bash demo/run_scenarioA.sh         # -> caps/A0,A1 ; restart agent @RAG_CHUNKS=12 for A2
bash demo/run_scenarioC.sh         # -> caps/C_gate.txt, caps/C_broken.txt (self-managing)

# 2. Scenario B — in-process seeded chaos (good agent degrades gracefully).
uv run --project "$ROOT" python demo/run_scenarioB.py   # -> caps/B1_chaos.txt, B2_reproduce.txt

# 3. Render terminal screenshots + explainer diagrams (Node + sharp).
cd demo && npm install && node make_screens.mjs && node make_diagrams.mjs && cd ..

# 4. Voiceover (ElevenLabs) and AI b-roll (fal.ai) — both have local fallbacks.
uv run --project "$ROOT" python demo/voiceover.py        # -> assets/vo/*.mp3
uv run --project "$ROOT" python demo/falai_broll.py      # -> assets/broll_title.mp4, broll_outro.mp4

# 5. Assemble + verify.
uv run --project "$ROOT" python demo/build_video.py      # -> agentchaos-demo.mp4 (+720p)
ffprobe -v error -show_entries format=duration -of csv=p=0 demo/agentchaos-demo.mp4
```

## File map
| File | Role |
|------|------|
| `storyboard.json` | **Source of truth** — scenes, assets, captions, narration lines |
| `narration.md` / `storyboard.md` | Human-readable script + scene table |
| `run_scenarioA.sh` | Cost-regression capture (real CLI, cross-process) |
| `run_scenarioB.py` | In-process seeded chaos (good agent) + reproducibility |
| `run_scenarioC.sh` | CI-gate capture; self-manages the :8080 / :8090 servers |
| `run_broken_chaos.py` | Chaos against the broken-fallback agent (exit 4) |
| `chaos_driver.py` | Shared in-process chaos harness (serves agent+tools, runs coordinator) |
| `broken_agent.py` | Demo-only refund agent **without** a graceful fallback |
| `make_screens.mjs` | caps/*.txt → `assets/shot_*.png` (dark terminal theme) |
| `make_diagrams.mjs` | `assets/diagram_*.png` (dev loop, chaos proxy, cause detection) |
| `voiceover.py` | Per-scene VO MP3s (ElevenLabs → `say` fallback) |
| `falai_broll.py` | Title/outro AI clips (fal.ai → ffmpeg card fallback) |
| `build_video.py` | ffmpeg assembly → `agentchaos-demo.mp4` (+ 720p) |

Generated binaries (`*.mp4`, `assets/`, `runs/`, `out/`, `node_modules/`) are
gitignored; the scripts and captured `caps/*.txt` are the durable artifacts.
