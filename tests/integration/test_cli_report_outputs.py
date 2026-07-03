"""End-to-end tests for `run --md-out` / `--junit-out` against a threaded server."""
from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from typer.testing import CliRunner

from agentchaos.cli import app
from agentchaos.report.markdown import comment_marker
from tests.integration.test_cli import (  # noqa: F401
    _write_scenario,
    expensive_server,
    happy_server,
)

pytestmark = pytest.mark.integration


def test_run_md_out_writes_report(tmp_path: Path, happy_server: str) -> None:  # noqa: F811
    sc = tmp_path / "s.yaml"
    _write_scenario(sc, happy_server, cost_limit=1.0)
    md = tmp_path / "r.md"
    runner = CliRunner()
    result = runner.invoke(
        app, ["run", str(sc), "--out", str(tmp_path / "t.jsonl"), "--md-out", str(md)]
    )
    assert result.exit_code == 0
    assert md.exists()
    content = md.read_text(encoding="utf-8")
    assert content.split("\n")[0] == comment_marker("refund-agent")
    assert "✅ PASS" in content


def test_run_junit_out_with_baseline_failure(
    tmp_path: Path, happy_server: str, expensive_server: str  # noqa: F811
) -> None:
    sc = tmp_path / "s.yaml"
    _write_scenario(sc, happy_server, cost_limit=1.0, rag_limit=True)
    baseline = tmp_path / "baseline.jsonl"
    runner = CliRunner()
    r1 = runner.invoke(app, ["run", str(sc), "--out", str(baseline), "--quiet"])
    assert r1.exit_code == 0

    _write_scenario(sc, expensive_server, cost_limit=1.0, rag_limit=True)
    md = tmp_path / "r.md"
    junit = tmp_path / "junit.xml"
    r2 = runner.invoke(
        app,
        [
            "run", str(sc),
            "--out", str(tmp_path / "candidate.jsonl"),
            "--baseline", str(baseline),
            "--md-out", str(md),
            "--junit-out", str(junit),
        ],
    )
    assert r2.exit_code == 2

    root = ET.fromstring(junit.read_text(encoding="utf-8"))
    suite = root.find("testsuite")
    assert suite is not None
    assert suite.get("failures") == "1"
    failure = suite.find("testcase[@name='check_regression_budget']/failure")
    assert failure is not None

    md_content = md.read_text(encoding="utf-8")
    assert "❌ FAIL" in md_content
    cost_row = next(line for line in md_content.split("\n") if line.startswith("| Cost |"))
    assert "+" in cost_row
    assert "❌ FAIL" in cost_row


def test_reports_written_under_quiet_and_json(
    tmp_path: Path, happy_server: str  # noqa: F811
) -> None:
    sc = tmp_path / "s.yaml"
    _write_scenario(sc, happy_server, cost_limit=1.0)
    runner = CliRunner()

    md_q = tmp_path / "quiet.md"
    junit_q = tmp_path / "quiet.xml"
    r_quiet = runner.invoke(
        app,
        [
            "run", str(sc), "--out", str(tmp_path / "q.jsonl"), "--quiet",
            "--md-out", str(md_q), "--junit-out", str(junit_q),
        ],
    )
    assert r_quiet.exit_code == 0
    assert md_q.exists()
    assert junit_q.exists()

    md_j = tmp_path / "json.md"
    junit_j = tmp_path / "json.xml"
    r_json = runner.invoke(
        app,
        [
            "run", str(sc), "--out", str(tmp_path / "j.jsonl"), "--json",
            "--md-out", str(md_j), "--junit-out", str(junit_j),
        ],
    )
    assert r_json.exit_code == 0
    assert md_j.exists()
    assert junit_j.exists()


def test_md_out_creates_parent_dirs(tmp_path: Path, happy_server: str) -> None:  # noqa: F811
    sc = tmp_path / "s.yaml"
    _write_scenario(sc, happy_server, cost_limit=1.0)
    md = tmp_path / "deep" / "nested" / "r.md"
    runner = CliRunner()
    result = runner.invoke(
        app, ["run", str(sc), "--out", str(tmp_path / "t.jsonl"), "--md-out", str(md)]
    )
    assert result.exit_code == 0
    assert md.exists()


def test_md_out_path_is_directory_errors(tmp_path: Path, happy_server: str) -> None:  # noqa: F811
    sc = tmp_path / "s.yaml"
    _write_scenario(sc, happy_server, cost_limit=1.0)
    target = tmp_path / "already-a-dir"
    target.mkdir()
    runner = CliRunner()
    result = runner.invoke(
        app, ["run", str(sc), "--out", str(tmp_path / "t.jsonl"), "--md-out", str(target)]
    )
    assert result.exit_code == 1
    output = result.stderr if result.stderr else result.output
    assert "report write error" in output
