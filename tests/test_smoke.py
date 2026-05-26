"""Phase 0 smoke tests."""
from __future__ import annotations

from typer.testing import CliRunner

from agentchaos import __version__
from agentchaos.cli import app


def test_version_constant_set() -> None:
    # Version is read from package metadata (single source of truth in
    # pyproject.toml); assert it is set and PEP 440-ish, not a literal value.
    assert __version__
    assert __version__[0].isdigit()


def test_cli_version_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_cli_help_lists_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("init", "doctor", "run", "compare"):
        assert cmd in result.stdout
