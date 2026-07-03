#!/usr/bin/env bash
# Scenario A: catch a cost regression in CI (real CLI, cross-process).
# Assumes tools server on :8090 and agent server on :8080 are already running.
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=/Users/noraxu/workspace/agentchaos
AC=(uv run --project "$ROOT" python -m agentchaos.cli)
CAPS=demo/caps
mkdir -p "$CAPS" demo/runs

echo "########## doctor ##########"
"${AC[@]}" doctor scenarios/01-happy-path.yaml 2>&1 | tee "$CAPS/A0_doctor.txt"

echo
echo "########## baseline run (rag_chunks=5) ##########"
"${AC[@]}" run scenarios/02-rag-cost-regression.yaml --out demo/runs/baseline.jsonl 2>&1 | tee "$CAPS/A1_baseline.txt"
echo "exit=${PIPESTATUS[0]}" | tee -a "$CAPS/A1_baseline.txt"
