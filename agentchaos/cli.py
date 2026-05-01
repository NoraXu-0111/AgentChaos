"""AgentChaos CLI entry point."""
from __future__ import annotations

import typer

from agentchaos import __version__

app = typer.Typer(
    name="agentchaos",
    help="Reliability testing for tool-using AI agents.",
    no_args_is_help=True,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """AgentChaos — reliability testing for tool-using AI agents."""


@app.command()
def init(
    directory: str = typer.Argument(".", help="Target directory."),
) -> None:
    """Scaffold a new scenario folder. (Phase 7 — not yet implemented.)"""
    typer.echo(f"init: would scaffold {directory} (not yet implemented)")
    raise typer.Exit(code=1)


@app.command()
def doctor(
    scenario: str | None = typer.Argument(None, help="Optional scenario file to validate."),
) -> None:
    """Validate scenario and ping endpoint. (Phase 7 — not yet implemented.)"""
    typer.echo(f"doctor: would check {scenario or 'config'} (not yet implemented)")
    raise typer.Exit(code=1)


@app.command()
def run(
    scenario: str = typer.Argument(..., help="Scenario YAML file."),
    out: str | None = typer.Option(None, "--out", help="Trace output path."),
    baseline: str | None = typer.Option(None, "--baseline", help="Baseline trace path."),
) -> None:
    """Execute a scenario and emit a trace. (Phase 7 — not yet implemented.)"""
    typer.echo(f"run: would execute {scenario} (not yet implemented)")
    raise typer.Exit(code=1)


@app.command()
def compare(
    baseline: str = typer.Argument(..., help="Baseline trace path."),
    candidate: str = typer.Argument(..., help="Candidate trace path."),
) -> None:
    """Diff two existing traces. (Phase 7 — not yet implemented.)"""
    typer.echo(f"compare: would diff {baseline} vs {candidate} (not yet implemented)")
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
