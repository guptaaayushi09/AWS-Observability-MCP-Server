"""The `query_cloudwatch_metrics` MCP tool.

Wraps CloudWatch GetMetricData, then summarizes the series (p50/p95/max/latest + a small
sample) so the model never receives a raw 100k-point payload.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from ..app import READ_ONLY, mcp
from ..aws.cloudwatch import get_metric_data
from ..formatting import summarize_series


class MetricSummary(BaseModel):
    """Summarized result of a metric query — stats first, raw points only as a sample."""

    namespace: str
    metric_name: str
    stat: str
    period_seconds: int
    datapoint_count: int = Field(description="Total datapoints returned by CloudWatch.")
    p50: float | None = Field(description="Median value across the window.")
    p95: float | None = Field(description="95th-percentile value; highlights spikes.")
    max: float | None
    min: float | None
    latest: float | None = Field(description="Most recent datapoint in the window.")
    sample: list[float] = Field(description="Most recent datapoints (truncated).")
    truncated: bool = Field(description="True if the full series was longer than the sample.")
    note: str | None = Field(default=None, description="Guidance when no data was found.")


@mcp.tool(annotations=READ_ONLY)
def query_cloudwatch_metrics(
    namespace: str,
    metric_name: str,
    dimensions: list[dict[str, str]],
    start_time: datetime,
    end_time: datetime,
    stat: str = "Average",
    period_seconds: int = 60,
) -> MetricSummary:
    """Query a CloudWatch metric over a time window and return summarized statistics.

    Use this to check the shape of a metric during an incident (e.g. a 5xx-count or latency
    spike). Returns p50/p95/max/min/latest plus a truncated sample of the most recent
    datapoints — never the full raw series.

    Args:
        namespace: CloudWatch namespace, e.g. "AWS/ApplicationELB" or "MyApp".
        metric_name: Metric name, e.g. "HTTPCode_Target_5XX_Count".
        dimensions: Filter dimensions as [{"Name": "Service", "Value": "checkout"}].
        start_time: Window start (UTC).
        end_time: Window end (UTC).
        stat: Aggregation statistic — Average, Sum, Maximum, Minimum, SampleCount.
        period_seconds: Aggregation period in seconds (default 60).
    """
    points = get_metric_data(
        namespace=namespace,
        metric_name=metric_name,
        dimensions=dimensions,
        stat=stat,
        period_seconds=period_seconds,
        start_time=start_time,
        end_time=end_time,
    )
    values = [v for _, v in points]
    summary = summarize_series(values)

    note = None
    if summary["datapoint_count"] == 0:
        note = (
            "No datapoints found. Verify the namespace, metric_name, and dimensions match a "
            "real metric, and that the time window covers when the metric was emitted. Call "
            "list_recent_alarms to discover active metrics/resources."
        )

    return MetricSummary(
        namespace=namespace,
        metric_name=metric_name,
        stat=stat,
        period_seconds=period_seconds,
        note=note,
        **summary,
    )
