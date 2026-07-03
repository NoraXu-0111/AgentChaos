"""Tests for the JUnit XML report renderer."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from agentchaos.profile.metrics import Metrics
from agentchaos.report.junit import CHECK_KINDS, render_junit
from agentchaos.verdict import Verdict
from agentchaos.violations import Violation

_XSD_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "junit-10.xsd"


def _pass_verdict() -> Verdict:
    return Verdict(outcome="pass", violations=[], exit_code=0)


def _fail_verdict() -> Verdict:
    return Verdict(
        outcome="fail",
        violations=[
            Violation(kind="budget", name="max_cost_usd", detail="cost $0.09 over limit $0.05"),
            Violation(kind="budget", name="max_tool_calls", detail="9 tool calls over limit 8"),
            Violation(kind="detector", name="loop", detail="get_order repeated 6x"),
        ],
        exit_code=2,
    )


def test_pass_run_six_testcases() -> None:
    xml = render_junit(
        scenario_name="refund-demo",
        verdict=_pass_verdict(),
        metrics=Metrics(total_latency_ms=1234),
    )
    root = ET.fromstring(xml)
    assert root.tag == "testsuites"
    suites = root.findall("testsuite")
    assert len(suites) == 1
    suite = suites[0]
    assert suite.get("name") == "agentchaos.refund-demo"
    assert suite.get("tests") == "6"
    assert suite.get("failures") == "0"
    assert suite.get("errors") == "0"
    cases = suite.findall("testcase")
    assert [c.get("name") for c in cases] == [f"check_{k}" for k in CHECK_KINDS]
    assert cases[0].get("name") == "check_expectation"
    assert cases[-1].get("name") == "check_replay"
    for case in cases:
        assert case.find("failure") is None


def test_failing_run_groups_violations_by_kind() -> None:
    xml = render_junit(
        scenario_name="refund-demo",
        verdict=_fail_verdict(),
        metrics=Metrics(total_latency_ms=500),
    )
    root = ET.fromstring(xml)
    suite = root.find("testsuite")
    assert suite is not None
    assert suite.get("failures") == "2"
    assert root.get("failures") == "2"
    cases = {c.get("name"): c for c in suite.findall("testcase")}

    budget_failure = cases["check_budget"].find("failure")
    assert budget_failure is not None
    assert budget_failure.get("message") == "2 budget violation(s)"
    assert budget_failure.get("type") == "AgentChaosViolation"
    assert budget_failure.text is not None
    assert "max_cost_usd: cost $0.09 over limit $0.05" in budget_failure.text
    assert "max_tool_calls: 9 tool calls over limit 8" in budget_failure.text

    detector_failure = cases["check_detector"].find("failure")
    assert detector_failure is not None
    assert detector_failure.get("message") == "1 detector violation(s)"

    for name in ("check_expectation", "check_regression_budget", "check_chaos", "check_replay"):
        assert cases[name].find("failure") is None


def test_xml_special_chars_escaped() -> None:
    detail = '<b>&"cost" ]]> spike</b>'
    verdict = Verdict(
        outcome="fail",
        violations=[Violation(kind="budget", name="max_cost_usd", detail=detail)],
        exit_code=2,
    )
    xml = render_junit(scenario_name="t", verdict=verdict, metrics=Metrics())
    root = ET.fromstring(xml)
    failure = root.find(".//testcase[@name='check_budget']/failure")
    assert failure is not None
    assert failure.text == f"max_cost_usd: {detail}"


def test_fixed_timestamp_deterministic() -> None:
    ts = datetime(2026, 7, 2, 12, 0, 0, tzinfo=UTC)
    first = render_junit(
        scenario_name="t", verdict=_pass_verdict(), metrics=Metrics(), timestamp=ts
    )
    second = render_junit(
        scenario_name="t", verdict=_pass_verdict(), metrics=Metrics(), timestamp=ts
    )
    assert first == second
    suite = ET.fromstring(first).find("testsuite")
    assert suite is not None
    assert suite.get("timestamp") == "2026-07-02T12:00:00"


def test_validates_against_junit_xsd() -> None:
    lxml_etree = pytest.importorskip("lxml.etree")
    schema = lxml_etree.XMLSchema(lxml_etree.parse(str(_XSD_PATH)))
    for verdict in (_pass_verdict(), _fail_verdict()):
        xml = render_junit(
            scenario_name="refund-demo",
            verdict=verdict,
            metrics=Metrics(total_latency_ms=1234),
            timestamp=datetime(2026, 7, 2, 12, 0, 0, tzinfo=UTC),
        )
        doc = lxml_etree.fromstring(xml.encode())
        schema.assertValid(doc)


def test_zero_latency_time_attr() -> None:
    xml = render_junit(scenario_name="t", verdict=_pass_verdict(), metrics=Metrics())
    root = ET.fromstring(xml)
    assert root.get("time") == "0.000"
    suite = root.find("testsuite")
    assert suite is not None
    assert suite.get("time") == "0.000"
