#!/usr/bin/env bash
# Scenario C — the CI gate.
#
# Runs the same agent through three checks and shows AgentChaos returning a
# distinct exit code per failure class, so CI can block the merge:
#   0  clean change ............................ merge proceeds
#   2  cost / budget regression ................ BLOCKED
#   4  agent crashed under injected chaos ...... BLOCKED  (3 = bad fallback path)
#
# Self-managing: starts the tools server (:8090) and restarts the agent (:8080)
# at the rag_chunks setting each step needs, then runs the in-process chaos check.
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=/Users/noraxu/workspace/agentchaos
AC=(uv run --project "$ROOT" python -m agentchaos.cli)
CAPS=demo/caps
OUT=demo/out
mkdir -p "$CAPS" demo/runs "$OUT"

GATE="$CAPS/C_gate.txt"
: > "$GATE"
say() { echo "$@" | tee -a "$GATE"; }

start_tools() {
  pgrep -f "uvicorn tools.main:app .*8090" >/dev/null 2>&1 && return 0
  TOOLS_BASE_URL=http://127.0.0.1:8090 uv run --project "$ROOT" \
    uvicorn tools.main:app --host 127.0.0.1 --port 8090 --log-level warning \
    >"$OUT/tools.log" 2>&1 &
  for _ in $(seq 1 40); do
    curl -sf -m1 http://127.0.0.1:8090/health >/dev/null 2>&1 && return 0
    sleep 0.25
  done
  echo "tools failed to start" >&2; return 1
}

restart_agent() {  # $1 = rag_chunks value
  local rc="$1"
  pkill -f "uvicorn server.main:app .*8080" >/dev/null 2>&1 || true
  sleep 0.4
  RAG_CHUNKS="$rc" TOOLS_BASE_URL=http://127.0.0.1:8090 uv run --project "$ROOT" \
    uvicorn server.main:app --host 127.0.0.1 --port 8080 --log-level warning \
    >"$OUT/agent.log" 2>&1 &
  for _ in $(seq 1 40); do
    curl -sf -m1 http://127.0.0.1:8080/health >/dev/null 2>&1 && return 0
    sleep 0.25
  done
  echo "agent failed to start" >&2; return 1
}

start_tools

say "########## CI GATE: three checks, one merge decision ##########"
say ""

# 1) Clean change — baseline at rag_chunks=5 → exit 0.
restart_agent 5
say "\$ agentchaos run scenarios/02-rag-cost-regression.yaml"
"${AC[@]}" run scenarios/02-rag-cost-regression.yaml --out demo/runs/baseline.jsonl \
  --quiet 2>>"$OUT/agent.log"
C1=$?
say "  -> exit $C1   (clean change: merge proceeds)"
say ""

# 2) Cost regression — same scenario, agent now at rag_chunks=12 → exit 2.
restart_agent 12
say "\$ agentchaos run scenarios/02-rag-cost-regression.yaml --baseline baseline.jsonl   # rag_chunks 5->12"
"${AC[@]}" run scenarios/02-rag-cost-regression.yaml \
  --baseline demo/runs/baseline.jsonl --out demo/runs/candidate.jsonl \
  --quiet 2>>"$OUT/agent.log"
C2=$?
say "  -> exit $C2   (cost regression: BLOCKED)"
say ""

# 3) Broken fallback under chaos — in-process broken agent crashes on a 503 → exit 4.
restart_agent 5
say "\$ agentchaos run scenarios/chaos-get-order.yaml   # broken agent, no fallback"
uv run --project "$ROOT" python demo/run_broken_chaos.py >/dev/null 2>>"$OUT/agent.log"
C3=$?
say "  -> exit $C3   (agent crashed under chaos: BLOCKED)"
say ""

say "------------------------------------------------------------"
say "Gate summary:"
say "  clean ............... exit $C1   $([ "$C1" -eq 0 ] && echo PASS || echo FAIL)"
say "  cost regression ..... exit $C2   $([ "$C2" -ne 0 ] && echo BLOCKED || echo PASS)"
say "  chaos (broken) ...... exit $C3   $([ "$C3" -ne 0 ] && echo BLOCKED || echo PASS)"
say ""
if [ "$C1" -eq 0 ] && [ "$C2" -ne 0 ] && [ "$C3" -ne 0 ]; then
  say "Merge decision: BLOCKED — 2 of 3 checks failed. Fix before merging."
else
  say "Merge decision: unexpected exit codes ($C1/$C2/$C3)."
fi

# Leave the live agent at the baseline rag_chunks=5 for any later steps.
restart_agent 5 >/dev/null 2>&1 || true
