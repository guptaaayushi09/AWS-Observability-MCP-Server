"""The `list_recent_alarms` MCP tool.

Wraps CloudWatch DescribeAlarms and reduces each alarm to the fields that matter during an
incident: which metric, the threshold it breached, and when it last changed state.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..app import READ_ONLY, mcp
from ..aws.cloudwatch import describe_alarms


class Alarm(BaseModel):
    """A CloudWatch metric alarm, trimmed to the incident-relevant fields."""

    name: str
    state: str = Field(description="OK, ALARM, or INSUFFICIENT_DATA.")
    metric_name: str | None
    namespace: str | None
    statistic: str | None
    comparison: str | None = Field(
        default=None, description="e.g. GreaterThanThreshold."
    )
    threshold: float | None
    state_reason: str | None = Field(
        default=None, description="Why the alarm is in its current state."
    )
    state_updated_at: str | None = Field(
        default=None, description="When the alarm last changed state (UTC)."
    )


class AlarmList(BaseModel):
    """Summarized result of an alarm query."""

    state: str
    count: int
    alarms: list[Alarm]
    note: str | None = Field(default=None, description="Guidance when no alarms matched.")


@mcp.tool(annotations=READ_ONLY)
def list_recent_alarms(
    state: str = "ALARM",
    max_records: int = 25,
) -> AlarmList:
    """List CloudWatch metric alarms in a given state, newest state-change first.

    Use this to discover what is currently firing during an incident and which metrics to
    investigate next. Each alarm carries its metric, threshold, and last state-change time.

    Args:
        state: Alarm state to filter by — ALARM, OK, or INSUFFICIENT_DATA (default ALARM).
        max_records: Maximum number of alarms to return (default 25).
    """
    raw = describe_alarms(state=state, max_records=max_records)

    alarms = [
        Alarm(
            name=a.get("AlarmName", ""),
            state=a.get("StateValue", state),
            metric_name=a.get("MetricName"),
            namespace=a.get("Namespace"),
            statistic=a.get("Statistic"),
            comparison=a.get("ComparisonOperator"),
            threshold=a.get("Threshold"),
            state_reason=a.get("StateReason"),
            state_updated_at=(
                a["StateUpdatedTimestamp"].isoformat()
                if a.get("StateUpdatedTimestamp")
                else None
            ),
        )
        for a in raw
    ]
    # Newest state change first so the freshest signal leads.
    alarms.sort(key=lambda a: a.state_updated_at or "", reverse=True)

    note = None
    if not alarms:
        note = (
            f"No alarms in state '{state}'. This may mean nothing is firing, or alarms are "
            "in a different state — try state='INSUFFICIENT_DATA' or state='OK'."
        )

    return AlarmList(state=state, count=len(alarms), alarms=alarms, note=note)
