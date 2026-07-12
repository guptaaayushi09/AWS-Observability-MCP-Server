"""CloudWatch metric + alarm wrappers over boto3.

Thin functions that make the AWS call and return plain Python structures. No truncation or
MCP concerns live here so the layer can be unit-tested directly against moto.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .clients import get_client


def get_metric_data(
    namespace: str,
    metric_name: str,
    dimensions: list[dict[str, str]],
    stat: str,
    period_seconds: int,
    start_time: datetime,
    end_time: datetime,
    region: str | None = None,
) -> list[tuple[datetime, float]]:
    """Fetch a single metric series via CloudWatch GetMetricData.

    Returns ``(timestamp, value)`` tuples sorted oldest-first. CloudWatch returns points
    newest-first and paginates with ``NextToken``; both are handled here.
    """
    client = get_client("cloudwatch", region)
    query = {
        "Id": "m1",
        "MetricStat": {
            "Metric": {
                "Namespace": namespace,
                "MetricName": metric_name,
                "Dimensions": dimensions,
            },
            "Period": period_seconds,
            "Stat": stat,
        },
        "ReturnData": True,
    }

    points: list[tuple[datetime, float]] = []
    next_token: str | None = None
    while True:
        kwargs: dict[str, Any] = {
            "MetricDataQueries": [query],
            "StartTime": start_time,
            "EndTime": end_time,
        }
        if next_token:
            kwargs["NextToken"] = next_token
        resp = client.get_metric_data(**kwargs)

        result = resp["MetricDataResults"][0]
        points.extend(zip(result["Timestamps"], result["Values"]))

        next_token = resp.get("NextToken")
        if not next_token:
            break

    points.sort(key=lambda p: p[0])
    return points


def describe_alarms(
    state: str,
    max_records: int,
    region: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch metric alarms in a given state via CloudWatch DescribeAlarms."""
    client = get_client("cloudwatch", region)
    resp = client.describe_alarms(
        StateValue=state,
        AlarmTypes=["MetricAlarm"],
        MaxRecords=max_records,
    )
    return resp.get("MetricAlarms", [])
