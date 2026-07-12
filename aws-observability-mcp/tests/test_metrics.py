"""Tests for the query_cloudwatch_metrics tool against moto-mocked CloudWatch."""

from __future__ import annotations

from aws_observability_mcp.tools.metrics import query_cloudwatch_metrics

from conftest import seed_metric

NAMESPACE = "MyApp"
METRIC = "5xxCount"
DIMENSIONS = [{"Name": "Service", "Value": "checkout"}]


def test_summarizes_seeded_series(aws):
    start, end = seed_metric(
        NAMESPACE, METRIC, DIMENSIONS, values=[10, 20, 30, 40, 120]
    )

    result = query_cloudwatch_metrics(
        namespace=NAMESPACE,
        metric_name=METRIC,
        dimensions=DIMENSIONS,
        start_time=start,
        end_time=end,
        stat="Maximum",
        period_seconds=60,
    )

    assert result.datapoint_count == 5
    assert result.max == 120
    assert result.min == 10
    assert result.latest == 120
    assert result.p50 == 30
    assert result.truncated is False
    assert result.note is None


def test_sample_truncates_long_series(aws):
    values = [float(i) for i in range(50)]
    start, end = seed_metric(NAMESPACE, METRIC, DIMENSIONS, values=values)

    result = query_cloudwatch_metrics(
        namespace=NAMESPACE,
        metric_name=METRIC,
        dimensions=DIMENSIONS,
        start_time=start,
        end_time=end,
        stat="Maximum",
    )

    assert result.datapoint_count == 50
    assert result.truncated is True
    assert len(result.sample) == 20
    # Sample keeps the most recent points.
    assert result.sample[-1] == 49


def test_no_data_returns_actionable_note(aws):
    start, end = seed_metric(NAMESPACE, METRIC, DIMENSIONS, values=[1, 2, 3])

    result = query_cloudwatch_metrics(
        namespace=NAMESPACE,
        metric_name="DoesNotExist",
        dimensions=DIMENSIONS,
        start_time=start,
        end_time=end,
    )

    assert result.datapoint_count == 0
    assert result.max is None
    assert result.note is not None
    assert "list_recent_alarms" in result.note
