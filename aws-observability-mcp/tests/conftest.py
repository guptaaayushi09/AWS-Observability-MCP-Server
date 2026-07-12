"""Shared test fixtures.

`moto` mocks AWS at the boto3 API level, so no real AWS account or credentials are needed.
The `aws` fixture activates the mock for a test; helper seeders populate a synthetic
incident (a 5xx spike, a firing alarm, matching error logs) that tools can then read back.
"""

from __future__ import annotations

import datetime as dt
import os

import boto3
import pytest
from moto import mock_aws

REGION = "us-east-1"


@pytest.fixture
def aws():
    """Activate moto for the duration of a test and yield a region-bound context."""
    # Dummy creds so boto3 is satisfied even though moto intercepts the calls.
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
    os.environ["AWS_DEFAULT_REGION"] = REGION
    with mock_aws():
        yield REGION


def seed_metric(
    namespace: str,
    metric_name: str,
    dimensions: list[dict[str, str]],
    values: list[float],
    *,
    end: dt.datetime | None = None,
    step_seconds: int = 60,
) -> tuple[dt.datetime, dt.datetime]:
    """Write a series of datapoints ending at ``end`` (default: now), one per ``step``.

    Returns the (start, end) window covering the seeded points, ready to pass to a query.
    """
    end = end or dt.datetime.now(dt.timezone.utc)
    cw = boto3.client("cloudwatch", region_name=REGION)
    n = len(values)
    for i, value in enumerate(values):
        ts = end - dt.timedelta(seconds=step_seconds * (n - 1 - i))
        cw.put_metric_data(
            Namespace=namespace,
            MetricData=[{
                "MetricName": metric_name,
                "Dimensions": dimensions,
                "Timestamp": ts,
                "Value": value,
                "Unit": "Count",
            }],
        )
    start = end - dt.timedelta(seconds=step_seconds * n)
    return start, end + dt.timedelta(seconds=step_seconds)


def seed_logs(
    log_group: str,
    messages: list[str],
    *,
    stream: str = "test-stream",
    end: dt.datetime | None = None,
    step_seconds: int = 1,
) -> tuple[dt.datetime, dt.datetime]:
    """Create ``log_group`` and write ``messages`` as events, one per ``step`` seconds.

    Returns the (start, end) window covering the events, ready to pass to tail_logs.
    """
    end = end or dt.datetime.now(dt.timezone.utc)
    logs = boto3.client("logs", region_name=REGION)
    logs.create_log_group(logGroupName=log_group)
    logs.create_log_stream(logGroupName=log_group, logStreamName=stream)

    n = len(messages)
    events = []
    for i, message in enumerate(messages):
        ts = end - dt.timedelta(seconds=step_seconds * (n - 1 - i))
        events.append({"timestamp": int(ts.timestamp() * 1000), "message": message})
    if events:
        logs.put_log_events(
            logGroupName=log_group, logStreamName=stream, logEvents=events
        )

    start = end - dt.timedelta(seconds=step_seconds * n)
    return start, end + dt.timedelta(seconds=step_seconds)


def seed_alarm(
    name: str,
    *,
    metric_name: str,
    namespace: str,
    threshold: float,
    state: str = "ALARM",
    comparison: str = "GreaterThanThreshold",
    statistic: str = "Average",
) -> None:
    """Create a metric alarm and force it into ``state`` (default ALARM)."""
    cw = boto3.client("cloudwatch", region_name=REGION)
    cw.put_metric_alarm(
        AlarmName=name,
        MetricName=metric_name,
        Namespace=namespace,
        Statistic=statistic,
        ComparisonOperator=comparison,
        Threshold=threshold,
        Period=60,
        EvaluationPeriods=1,
    )
    cw.set_alarm_state(
        AlarmName=name, StateValue=state, StateReason="seeded for test"
    )


def seed_ecs_service(
    service_name: str,
    *,
    cluster: str = "test-cluster",
    desired_count: int = 3,
) -> str:
    """Create an ECS cluster + service via moto. Returns the cluster name."""
    ecs = boto3.client("ecs", region_name=REGION)
    ecs.create_cluster(clusterName=cluster)
    ecs.register_task_definition(
        family=f"{service_name}-task",
        containerDefinitions=[
            {"name": "app", "image": "app:latest", "memory": 128}
        ],
    )
    ecs.create_service(
        cluster=cluster,
        serviceName=service_name,
        taskDefinition=f"{service_name}-task",
        desiredCount=desired_count,
    )
    return cluster
