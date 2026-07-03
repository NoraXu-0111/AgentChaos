"""AgentChaos CLI entry point."""
from __future__ import annotations

import asyncio
import json as _json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Annotated

import httpx
import typer

from agentchaos import __version__
from agentchaos.detectors.runner import run_detectors
from agentchaos.detectors.schema import Finding
from agentchaos.otel.spans import SpanBuildError, build_spans
from agentchaos.profile.causes import find_causes
from agentchaos.profile.compare import diff as profile_diff
from agentchaos.profile.metrics import aggregate
from agentchaos.replay.detect import detect_replay_divergence
from agentchaos.replay.schema import Divergence
from agentchaos.replay.transport import REPLAY_ERROR_PREFIX, RecordedTransport
from agentchaos.report.terminal import render_terminal
from agentchaos.runner.coordinator import RunCoordinator
from agentchaos.scenario.loader import LoaderError, load_scenario, scenario_hash
from agentchaos.scenario.schema import AgentTarget, Scenario
from agentchaos.trace.reader import TraceReadError, read_trace
from agentchaos.trace.schema import RunMeta, TraceEvent, UserTurn
from agentchaos.transport.base import AgentTransport
from agentchaos.transport.http import HTTPTransport
from agentchaos.verdict import (
    EXIT_PASS,
    EXIT_TRANSPORT_FAIL,
    EXIT_USAGE_ERROR,
    Verdict,
    compute_verdict,
)

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
    version: Annotated[
        bool,
        typer.Option(
            "--version", "-V",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = False,
) -> None:
    """AgentChaos — reliability testing for tool-using AI agents."""


# ----------------------------------------------------------------------------
# init
# ----------------------------------------------------------------------------

_EXAMPLE_SCENARIO = """id: example
name: example
description: starter scenario — replace with your own
agent:
  type: http
  endpoint: http://127.0.0.1:8080/chat
  timeout_s: 30
conversation:
  - user: "hello"
expect:
  final_response_contains: ["hello"]
budgets:
  max_cost_usd: 0.10
  max_tool_calls: 5
  max_total_latency_ms: 8000
"""

_EXAMPLE_README = """# AgentChaos test directory

Edit `scenarios/example.yaml` to point at your agent endpoint, then:

    agentchaos doctor scenarios/example.yaml
    agentchaos run scenarios/example.yaml --out runs/baseline.jsonl
    # ...make a change to your agent...
    agentchaos run scenarios/example.yaml --baseline runs/baseline.jsonl
"""


@app.command()
def init(
    directory: Annotated[
        Path,
        typer.Argument(help="Target directory (created if missing)."),
    ] = Path("."),
    force: Annotated[bool, typer.Option("--force", "-f", help="Overwrite existing files.")] = False,
) -> None:
    """Scaffold a new AgentChaos scenario folder."""
    scenarios_dir = directory / "scenarios"
    runs_dir = directory / "runs"
    example = scenarios_dir / "example.yaml"
    readme = directory / "README.md"

    if example.exists() and not force:
        typer.secho(
            f"refusing to overwrite {example} (use --force to override)",
            err=True, fg=typer.colors.RED,
        )
        raise typer.Exit(code=EXIT_USAGE_ERROR)

    directory.mkdir(parents=True, exist_ok=True)
    scenarios_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / ".gitkeep").touch(exist_ok=True)
    example.write_text(_EXAMPLE_SCENARIO)
    if not readme.exists() or force:
        readme.write_text(_EXAMPLE_README)

    typer.echo(f"  Created {example}")
    typer.echo(f"  Created {runs_dir}/")
    typer.echo(f"  Created {readme}")
    typer.echo("")
    typer.echo("Next: agentchaos doctor scenarios/example.yaml")


# ----------------------------------------------------------------------------
# doctor
# ----------------------------------------------------------------------------

_LITERAL_ENV_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


async def _ping_endpoint(target: AgentTarget) -> tuple[bool, str]:
    """Probe the agent endpoint with a tiny payload. Returns (ok, detail)."""
    transport = HTTPTransport(target)
    try:
        t0 = time.perf_counter()
        try:
            res = await transport.send("doctor", "ping")
        except Exception as exc:
            return False, f"transport raised: {exc!r}"
        dt_ms = int((time.perf_counter() - t0) * 1000)
        if res.error is not None:
            return False, f"{res.error} ({dt_ms}ms)"
        return True, f"HTTP {res.status_code or 200}, {dt_ms}ms, fidelity={res.fidelity}"
    finally:
        await transport.aclose()


@app.command()
def doctor(
    scenario: Annotated[
        Path | None,
        typer.Argument(help="Optional scenario YAML to validate."),
    ] = None,
) -> None:
    """Validate scenario and (if provided) probe the agent endpoint."""
    errors = 0
    warnings = 0

    if scenario is None:
        typer.echo("(pass a scenario file to do full checks)")
        raise typer.Exit(code=EXIT_PASS)

    # Step 1: parse
    try:
        s = load_scenario(scenario)
    except LoaderError as exc:
        typer.secho(f"✗ Scenario failed to parse: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=EXIT_USAGE_ERROR) from None
    typer.echo(f"✓ Scenario parses ({s.name}, {len(s.conversation)} turn(s))")

    # Step 2: env-var expansion check
    leftover_vars: set[str] = set()
    for v in s.agent.headers.values():
        for m in _LITERAL_ENV_RE.findall(v):
            leftover_vars.add(m)
    if leftover_vars:
        warnings += 1
        for name in sorted(leftover_vars):
            typer.secho(
                f"⚠ env var {name} is referenced in headers but not set",
                fg=typer.colors.YELLOW,
            )

    # Step 3: ping endpoint
    ok, detail = asyncio.run(_ping_endpoint(s.agent))
    if ok:
        typer.echo(f"✓ Endpoint reachable: {s.agent.endpoint} ({detail})")
    else:
        errors += 1
        typer.secho(
            f"✗ Endpoint not reachable: {s.agent.endpoint} ({detail})",
            err=True, fg=typer.colors.RED,
        )

    typer.echo("")
    typer.echo(f"{warnings} warning(s), {errors} error(s).")
    if errors:
        raise typer.Exit(code=EXIT_TRANSPORT_FAIL)
    raise typer.Exit(code=EXIT_PASS)


# ----------------------------------------------------------------------------
# run
# ----------------------------------------------------------------------------


def _build_transport(target: AgentTarget) -> AgentTransport:
    """Indirection so tests can monkeypatch the transport."""
    return HTTPTransport(target)


def _default_out_path() -> Path:
    return Path("runs") / f"run-{datetime.now(UTC).strftime('%Y-%m-%dT%H-%M-%S')}.jsonl"


def _emit_json_verdict(
    verdict: Verdict,
    trace_path: Path,
    run_id: str,
    findings: list[Finding],
    *,
    divergences: list[Divergence] | None = None,
    mode: str | None = None,
) -> None:
    payload = {
        "outcome": verdict.outcome,
        "exit_code": verdict.exit_code,
        "violations": [v.model_dump() for v in verdict.violations],
        "findings": [f.model_dump() for f in findings],
        "trace_path": str(trace_path),
        "run_id": run_id,
    }
    if divergences is not None:
        payload["divergences"] = [d.model_dump() for d in divergences]
    if mode is not None:
        payload["mode"] = mode
    typer.echo(_json.dumps(payload, indent=2))


async def _execute_run(
    scenario: Scenario,
    scenario_path: Path,
    out_path: Path,
    baseline_path: Path | None,
    *,
    quiet: bool,
    json_output: bool,
    seed: int | None,
    strict_scenario: bool,
    transport: AgentTransport | None = None,
) -> int:
    if transport is None:
        transport = _build_transport(scenario.agent)
    # CLI --seed takes precedence over scenario.seed when explicitly passed.
    effective_seed = seed if seed is not None else scenario.seed
    coordinator = RunCoordinator(scenario, transport, seed=effective_seed)
    try:
        result = await coordinator.run_once(out_path, scenario_path=str(scenario_path))
    finally:
        await transport.aclose()

    candidate_trace: list[TraceEvent] = list(read_trace(result.trace_path))
    candidate_metrics = aggregate(candidate_trace)
    findings = run_detectors(candidate_trace, scenario.budgets)

    diff_obj = None
    causes: list = []
    if baseline_path is not None:
        try:
            baseline_trace = list(read_trace(baseline_path))
        except (FileNotFoundError, TraceReadError) as exc:
            typer.secho(f"✗ baseline trace error: {exc}", err=True, fg=typer.colors.RED)
            return EXIT_USAGE_ERROR
        baseline_metrics = aggregate(baseline_trace)
        candidate_hash = scenario_hash(scenario)
        baseline_hash = _baseline_scenario_hash(baseline_trace)
        drift = baseline_hash is not None and baseline_hash != candidate_hash
        if drift and strict_scenario:
            typer.secho("✗ scenario hash drift; refusing under --strict-scenario",
                        err=True, fg=typer.colors.RED)
            return EXIT_USAGE_ERROR
        diff_obj = profile_diff(baseline_metrics, candidate_metrics, scenario_drift=drift)
        causes = find_causes(baseline_trace, candidate_trace, diff_obj)

    verdict = compute_verdict(
        candidate_metrics,
        scenario.expect,
        scenario.budgets,
        diff=diff_obj,
        final_text=result.session.final_text,
        session_error=result.session.error,
        findings=findings,
        chaos=scenario.chaos,
        trace=candidate_trace,
    )

    if json_output:
        _emit_json_verdict(verdict, result.trace_path, result.run_id, findings)
    elif not quiet:
        typer.echo(
            render_terminal(
                scenario_name=scenario.name,
                verdict=verdict,
                metrics=candidate_metrics,
                diff=diff_obj,
                causes=causes,
                trace_path=result.trace_path,
                findings=findings,
            )
        )
    return verdict.exit_code


def _baseline_scenario_hash(trace: list[TraceEvent]) -> str | None:
    for ev in trace:
        if isinstance(ev, RunMeta):
            return ev.scenario_hash
    return None


@app.command()
def run(
    scenario: Annotated[Path, typer.Argument(help="Scenario YAML file.")],
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Trace output path."),
    ] = None,
    baseline: Annotated[
        Path | None,
        typer.Option("--baseline", help="Baseline trace to diff against."),
    ] = None,
    quiet: Annotated[bool, typer.Option("--quiet", help="Suppress the report.")] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable verdict.")
    ] = False,
    seed: Annotated[int | None, typer.Option("--seed", help="Deterministic seed.")] = None,
    strict_scenario: Annotated[
        bool, typer.Option("--strict-scenario", help="Fail on scenario hash drift."),
    ] = False,
) -> None:
    """Execute a scenario and emit a trace + verdict."""
    try:
        s = load_scenario(scenario)
    except LoaderError as exc:
        typer.secho(f"✗ {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=EXIT_USAGE_ERROR) from None

    out_path = out if out is not None else _default_out_path()
    code = asyncio.run(
        _execute_run(
            s,
            scenario,
            out_path,
            baseline,
            quiet=quiet,
            json_output=json_output,
            seed=seed,
            strict_scenario=strict_scenario,
        )
    )
    raise typer.Exit(code=code)


# ----------------------------------------------------------------------------
# replay
# ----------------------------------------------------------------------------


async def _execute_replay(
    scenario: Scenario,
    scenario_path: Path,
    recording_events: list[TraceEvent],
    out_path: Path,
    *,
    live: bool,
    quiet: bool,
    json_output: bool,
    transport: AgentTransport | None = None,
) -> int:
    """Run the scenario through a recorded (or live) transport and verdict with divergences."""
    # Replay never injects chaos and never starts the proxy.
    replay_scenario = scenario.model_copy(update={"chaos": None})
    if transport is None:
        transport = (
            _build_transport(scenario.agent) if live else RecordedTransport(recording_events)
        )
    coordinator = RunCoordinator(replay_scenario, transport)
    try:
        result = await coordinator.run_once(out_path, scenario_path=str(scenario_path))
    finally:
        await transport.aclose()

    candidate_trace: list[TraceEvent] = list(read_trace(result.trace_path))
    metrics = aggregate(candidate_trace)
    findings = run_detectors(candidate_trace, scenario.budgets)
    divergences = detect_replay_divergence(recording_events, candidate_trace)

    session_error = result.session.error
    if session_error is not None and session_error.startswith(REPLAY_ERROR_PREFIX):
        session_error = None

    verdict = compute_verdict(
        metrics,
        scenario.expect,
        scenario.budgets,
        final_text=result.session.final_text,
        session_error=session_error,
        findings=findings,
        chaos=None,
        trace=candidate_trace,
        divergences=divergences,
    )

    if json_output:
        _emit_json_verdict(
            verdict,
            result.trace_path,
            result.run_id,
            findings,
            divergences=divergences,
            mode="live" if live else "offline",
        )
    elif not quiet:
        typer.echo(
            render_terminal(
                scenario_name=scenario.name,
                verdict=verdict,
                metrics=metrics,
                diff=None,
                causes=[],
                trace_path=result.trace_path,
                findings=findings,
            )
        )
    return verdict.exit_code


@app.command()
def replay(
    scenario: Annotated[Path, typer.Argument(help="Scenario YAML file.")],
    recording: Annotated[Path, typer.Argument(help="Recorded trace from a prior `run --out`.")],
    out: Annotated[Path | None, typer.Option("--out", help="Replay trace output path.")] = None,
    live: Annotated[
        bool,
        typer.Option("--live", help="Run the agent live and check divergence vs the recording."),
    ] = False,
    quiet: Annotated[bool, typer.Option("--quiet", help="Suppress the report.")] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable verdict.")
    ] = False,
) -> None:
    """Replay a recorded trace (offline, zero live HTTP by default); exit 5 on divergence."""
    try:
        s = load_scenario(scenario)
    except LoaderError as exc:
        typer.secho(f"✗ {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=EXIT_USAGE_ERROR) from None

    try:
        recording_events: list[TraceEvent] = list(read_trace(recording))
    except (FileNotFoundError, TraceReadError) as exc:
        typer.secho(f"✗ recording trace error: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=EXIT_USAGE_ERROR) from None

    if not any(isinstance(e, UserTurn) for e in recording_events):
        typer.secho(
            "✗ recording contains no conversation turns", err=True, fg=typer.colors.RED
        )
        raise typer.Exit(code=EXIT_USAGE_ERROR)

    out_path = out if out is not None else _default_out_path()
    code = asyncio.run(
        _execute_replay(
            s,
            scenario,
            recording_events,
            out_path,
            live=live,
            quiet=quiet,
            json_output=json_output,
        )
    )
    raise typer.Exit(code=code)


# ----------------------------------------------------------------------------
# compare
# ----------------------------------------------------------------------------


@app.command()
def compare(
    baseline: Annotated[Path, typer.Argument(help="Baseline trace path.")],
    candidate: Annotated[Path, typer.Argument(help="Candidate trace path.")],
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable diff.")
    ] = False,
) -> None:
    """Diff two existing traces. Pure analysis — no agent calls."""
    try:
        b_trace = list(read_trace(baseline))
        c_trace = list(read_trace(candidate))
    except (FileNotFoundError, TraceReadError) as exc:
        typer.secho(f"✗ {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=EXIT_USAGE_ERROR) from None

    b_metrics = aggregate(b_trace)
    c_metrics = aggregate(c_trace)
    b_hash = _baseline_scenario_hash(b_trace)
    c_hash = _baseline_scenario_hash(c_trace)
    drift = b_hash is not None and c_hash is not None and b_hash != c_hash
    d = profile_diff(b_metrics, c_metrics, scenario_drift=drift)
    causes = find_causes(b_trace, c_trace, d)
    findings = run_detectors(c_trace, budget=None)

    # No scenario means no budgets/expectations to enforce — purely informational.
    verdict = Verdict(outcome="pass", violations=[], exit_code=EXIT_PASS)
    scenario_name = _scenario_name_from_trace(c_trace) or "compare"

    if json_output:
        payload = {
            "outcome": "pass",
            "exit_code": EXIT_PASS,
            "scenario_drift": drift,
            "deltas": [d.model_dump() for d in d.deltas],
            "causes": [c.model_dump() for c in causes],
            "findings": [f.model_dump() for f in findings],
        }
        typer.echo(_json.dumps(payload, indent=2))
    else:
        typer.echo(
            render_terminal(
                scenario_name=scenario_name,
                verdict=verdict,
                metrics=c_metrics,
                diff=d,
                causes=causes,
                trace_path=candidate,
                findings=findings,
            )
        )
    raise typer.Exit(code=EXIT_PASS)


def _scenario_name_from_trace(trace: list[TraceEvent]) -> str | None:
    for ev in trace:
        if isinstance(ev, RunMeta):
            return ev.scenario_name
    return None


# ----------------------------------------------------------------------------
# export-otel
# ----------------------------------------------------------------------------


def _load_otel_emit() -> ModuleType:
    """Import agentchaos.otel.emit lazily; ModuleNotFoundError means the otel extra is missing."""
    import agentchaos.otel.emit

    return agentchaos.otel.emit


def _parse_otel_headers(pairs: list[str]) -> dict[str, str]:
    """Parse repeatable KEY=VALUE --header values; raise typer.BadParameter on malformed input."""
    headers: dict[str, str] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            raise typer.BadParameter(
                f"expected KEY=VALUE, got {pair!r}", param_hint="--header"
            )
        headers[key] = value
    return headers


@app.command("export-otel")
def export_otel(
    trace: Annotated[Path, typer.Argument(help="Trace JSONL from a prior `run --out`.")],
    endpoint: Annotated[
        str,
        typer.Option("--endpoint", help="OTLP HTTP traces endpoint."),
    ] = "http://localhost:4318/v1/traces",
    header: Annotated[
        list[str] | None,
        typer.Option("--header", help="Extra OTLP header as KEY=VALUE (repeatable)."),
    ] = None,
    service_name: Annotated[
        str, typer.Option("--service-name", help="OTel service.name resource attribute."),
    ] = "agentchaos",
    timeout_s: Annotated[
        float, typer.Option("--timeout-s", help="Export timeout in seconds."),
    ] = 10.0,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print span specs as JSON lines to stdout; no export."),
    ] = False,
) -> None:
    """Export a trace to an OTLP collector as GenAI semantic-convention spans."""
    try:
        events: list[TraceEvent] = list(read_trace(trace))
        specs = build_spans(events)
    except (FileNotFoundError, TraceReadError, SpanBuildError) as exc:
        typer.secho(f"✗ {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=EXIT_USAGE_ERROR) from None

    if dry_run:
        for spec in specs:
            typer.echo(spec.model_dump_json())
        typer.echo(f"{len(specs)} span(s) (dry run)")
        raise typer.Exit(code=EXIT_PASS)

    headers = _parse_otel_headers(header or [])

    try:
        emit = _load_otel_emit()
    except ModuleNotFoundError:
        typer.secho(
            "✗ export-otel requires the otel extra: pip install 'agentchaos-reliability[otel]'",
            err=True, fg=typer.colors.RED,
        )
        raise typer.Exit(code=EXIT_USAGE_ERROR) from None

    service_version = next(
        (ev.agentchaos_version for ev in events if isinstance(ev, RunMeta)), None
    )
    exporter = emit.make_otlp_http_exporter(endpoint, headers=headers, timeout_s=timeout_s)
    try:
        count = emit.emit_spans(
            specs, exporter, service_name=service_name, service_version=service_version
        )
    except emit.OtelExportError as exc:
        typer.secho(f"✗ {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=EXIT_TRANSPORT_FAIL) from None
    typer.echo(f"Exported {count} span(s) to {endpoint}")
    raise typer.Exit(code=EXIT_PASS)


# Suppress unused-import warnings on these symbols (kept for re-export / typing).
_keep = (httpx, os)


if __name__ == "__main__":
    app()
