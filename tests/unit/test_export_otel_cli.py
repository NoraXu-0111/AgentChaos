"""CLI tests for `agentchaos export-otel` (CliRunner; no network, no otel required)."""
from __future__ import annotations

import json as _json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import agentchaos.cli as cli_module
from agentchaos.cli import app
from agentchaos.otel.spans import SpanSpec


def _combined(result) -> str:
    try:
        stderr = result.stderr
    except ValueError:
        stderr = ""
    return result.stdout + (stderr or "")


def test_export_otel_dry_run_prints_specs(otel_trace_file: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["export-otel", str(otel_trace_file), "--dry-run"])
    assert result.exit_code == 0, result.output
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines[-1].endswith("span(s) (dry run)")
    specs = [SpanSpec.model_validate(_json.loads(line)) for line in lines[:-1]]
    assert specs
    assert specs[0].parent_id is None
    assert specs[0].name.startswith("agentchaos.run ")


def test_export_otel_dry_run_works_without_otel(
    otel_trace_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom() -> None:
        raise ModuleNotFoundError("No module named 'opentelemetry'")

    monkeypatch.setattr(cli_module, "_load_otel_emit", _boom)
    runner = CliRunner()
    result = runner.invoke(app, ["export-otel", str(otel_trace_file), "--dry-run"])
    assert result.exit_code == 0, result.output


def test_export_otel_missing_extra_graceful(
    otel_trace_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom() -> None:
        raise ModuleNotFoundError("No module named 'opentelemetry'")

    monkeypatch.setattr(cli_module, "_load_otel_emit", _boom)
    runner = CliRunner()
    result = runner.invoke(app, ["export-otel", str(otel_trace_file)])
    assert result.exit_code == 1
    assert "pip install 'agentchaos-reliability[otel]'" in _combined(result)


def test_export_otel_missing_trace_file(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["export-otel", str(tmp_path / "missing.jsonl")])
    assert result.exit_code == 1


def test_export_otel_empty_trace_file(tmp_path: Path) -> None:
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    runner = CliRunner()
    result = runner.invoke(app, ["export-otel", str(empty)])
    assert result.exit_code == 1
    assert "run_meta" in _combined(result)


def test_export_otel_bad_header_format(otel_trace_file: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app, ["export-otel", str(otel_trace_file), "--header", "notakv"]
    )
    assert result.exit_code != 0
    assert "KEY=VALUE" in _combined(result)
