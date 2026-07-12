"""Tests for the list_recent_alarms tool against moto-mocked CloudWatch."""

from __future__ import annotations

from aws_observability_mcp.tools.alarms import list_recent_alarms

from conftest import seed_alarm


def test_lists_firing_alarms(aws):
    seed_alarm(
        "checkout-5xx",
        metric_name="5xxCount",
        namespace="MyApp",
        threshold=100,
        state="ALARM",
    )
    seed_alarm(
        "checkout-latency",
        metric_name="Latency",
        namespace="MyApp",
        threshold=500,
        state="ALARM",
    )

    result = list_recent_alarms(state="ALARM")

    assert result.count == 2
    names = {a.name for a in result.alarms}
    assert names == {"checkout-5xx", "checkout-latency"}
    firing = next(a for a in result.alarms if a.name == "checkout-5xx")
    assert firing.state == "ALARM"
    assert firing.metric_name == "5xxCount"
    assert firing.threshold == 100
    assert result.note is None


def test_state_filter_excludes_other_states(aws):
    seed_alarm(
        "firing", metric_name="M", namespace="MyApp", threshold=1, state="ALARM"
    )
    seed_alarm(
        "healthy", metric_name="M", namespace="MyApp", threshold=1, state="OK"
    )

    result = list_recent_alarms(state="ALARM")

    assert result.count == 1
    assert result.alarms[0].name == "firing"


def test_no_alarms_returns_note(aws):
    result = list_recent_alarms(state="ALARM")

    assert result.count == 0
    assert result.note is not None
