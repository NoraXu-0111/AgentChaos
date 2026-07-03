"""Structural tests for action.yml and the demo workflow."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ACTION_PATH = _REPO_ROOT / "action.yml"
_DEMO_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "agentchaos-demo.yml"


def _load_action() -> dict[str, Any]:
    return yaml.safe_load(_ACTION_PATH.read_text(encoding="utf-8"))


def test_action_yml_parses_and_is_composite() -> None:
    action = _load_action()
    assert action["name"] == "AgentChaos"
    assert action["runs"]["using"] == "composite"
    for step in action["runs"]["steps"]:
        if "run" in step:
            assert step.get("shell") == "bash", f"step {step.get('name')} missing shell: bash"


def test_action_inputs_complete() -> None:
    action = _load_action()
    expected_inputs = {
        "scenario", "baseline", "out", "md-out", "junit-out", "seed",
        "comment", "github-token", "fail-on", "package", "python-version",
        "working-directory",
    }
    inputs = action["inputs"]
    assert expected_inputs <= set(inputs)
    required = {name for name, spec in inputs.items() if spec.get("required")}
    assert required == {"scenario"}
    expected_outputs = {"exit-code", "outcome", "md-path", "junit-path", "trace-path"}
    assert expected_outputs <= set(action["outputs"])


def test_comment_step_guarded_and_uses_marker() -> None:
    action = _load_action()
    comment_step = next(
        s for s in action["runs"]["steps"] if s.get("name") == "Post PR comment"
    )
    assert "pull_request" in comment_step["if"]
    script = comment_step["run"]
    assert "head -n1" in script
    assert "-X PATCH" in script
    assert "-X POST" in script
    assert script.count("::warning::") >= 2


def test_demo_workflow_exists_and_has_pr_write() -> None:
    workflow = yaml.safe_load(_DEMO_WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert workflow["permissions"]["pull-requests"] == "write"
    # yaml parses the `on:` key as boolean True.
    triggers = workflow.get("on") or workflow.get(True)
    assert "pull_request" in triggers
    steps = workflow["jobs"]["demo"]["steps"]
    gate = next(s for s in steps if s.get("uses") == "./")
    assert gate["with"]["scenario"] == "scenarios/02-rag-cost-regression.yaml"
    assert gate["with"]["baseline"] == "runs/baseline-ci.jsonl"
    assert gate["with"]["fail-on"] == ""
