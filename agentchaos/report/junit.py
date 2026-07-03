"""JUnit XML report — one testsuite per run, one testcase per check kind."""
from __future__ import annotations

from datetime import UTC, datetime
from xml.etree import ElementTree as ET

from agentchaos.profile.metrics import Metrics
from agentchaos.verdict import Verdict
from agentchaos.violations import Violation, ViolationKind

CHECK_KINDS: tuple[ViolationKind, ...] = (
    "expectation", "budget", "regression_budget", "detector", "chaos", "replay",
)


def render_junit(
    *,
    scenario_name: str,
    verdict: Verdict,
    metrics: Metrics,
    timestamp: datetime | None = None,
) -> str:
    """Render the run as a JUnit XML string.

    Structure: ``<testsuites>`` root, one ``<testsuite>``, and exactly one
    ``<testcase>`` per check kind in :data:`CHECK_KINDS`. Violations of a kind
    collapse into that testcase's single ``<failure>``.
    """
    by_kind: dict[ViolationKind, list[Violation]] = {kind: [] for kind in CHECK_KINDS}
    for violation in verdict.violations:
        by_kind[violation.kind].append(violation)

    failures = sum(1 for kind in CHECK_KINDS if by_kind[kind])
    time_attr = f"{(metrics.total_latency_ms or 0) / 1000:.3f}"
    ts = (timestamp or datetime.now(UTC)).replace(tzinfo=None).isoformat(timespec="seconds")

    root = ET.Element(
        "testsuites",
        tests=str(len(CHECK_KINDS)),
        failures=str(failures),
        errors="0",
        time=time_attr,
    )
    suite = ET.SubElement(
        root,
        "testsuite",
        name=f"agentchaos.{scenario_name}",
        tests=str(len(CHECK_KINDS)),
        failures=str(failures),
        errors="0",
        skipped="0",
        time=time_attr,
        timestamp=ts,
    )
    for kind in CHECK_KINDS:
        case = ET.SubElement(
            suite,
            "testcase",
            name=f"check_{kind}",
            classname=f"agentchaos.{scenario_name}",
            time="0.000",
        )
        kind_violations = by_kind[kind]
        if kind_violations:
            failure = ET.SubElement(
                case,
                "failure",
                message=f"{len(kind_violations)} {kind} violation(s)",
                type="AgentChaosViolation",
            )
            failure.text = "\n".join(f"{v.name}: {v.detail}" for v in kind_violations)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode()
