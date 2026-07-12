"""The `tail_logs` MCP tool.

Wraps CloudWatch Logs FilterLogEvents, then groups similar lines into error patterns so the
model sees "5× connection refused" instead of a raw wall of near-identical log lines.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from ..app import READ_ONLY, mcp
from ..aws.logs import filter_log_events
from ..formatting import summarize_log_events


class LogLine(BaseModel):
    """A single log event, trimmed to timestamp + message."""

    timestamp: int | None = Field(description="Event time in epoch milliseconds.")
    message: str


class ErrorPattern(BaseModel):
    """A normalized log template with the number of lines that collapsed into it."""

    pattern: str = Field(description="Log line with IDs/numbers/timestamps masked.")
    count: int


class LogSummary(BaseModel):
    """Summarized result of a log query — grouped patterns first, raw lines as a sample."""

    log_group: str
    filter_pattern: str | None
    event_count: int = Field(description="Total matching events fetched (capped at limit).")
    error_patterns: list[ErrorPattern] = Field(
        description="Distinct error templates with counts, most frequent first."
    )
    sample: list[LogLine] = Field(description="Most recent matching lines (truncated).")
    truncated: bool = Field(description="True if more lines matched than were sampled.")
    note: str | None = Field(default=None, description="Guidance when no events were found.")


@mcp.tool(annotations=READ_ONLY)
def tail_logs(
    log_group: str,
    start_time: datetime,
    end_time: datetime,
    filter_pattern: str | None = None,
    limit: int = 50,
) -> LogSummary:
    """Tail a CloudWatch log group over a time window and group similar errors.

    Returns the most recent matching lines plus a summary of distinct error patterns (with
    counts) so repeated errors collapse into one entry. Use an incident time window and an
    optional filter_pattern like "ERROR" or "5xx" to narrow the search.

    Args:
        log_group: The CloudWatch log group name, e.g. "/ecs/checkout-service".
        start_time: Window start (UTC).
        end_time: Window end (UTC).
        filter_pattern: Optional CloudWatch Logs filter pattern, e.g. "ERROR".
        limit: Maximum number of events to fetch (default 50).
    """
    events = filter_log_events(
        log_group=log_group,
        start_time=start_time,
        end_time=end_time,
        filter_pattern=filter_pattern,
        limit=limit,
    )
    summary = summarize_log_events(events)

    note = None
    if summary["event_count"] == 0:
        note = (
            "No log events matched. Verify the log_group exists and the time window covers "
            "the incident. Loosen or remove filter_pattern if it may be too specific."
        )

    return LogSummary(
        log_group=log_group,
        filter_pattern=filter_pattern,
        event_count=summary["event_count"],
        error_patterns=[ErrorPattern(**p) for p in summary["error_patterns"]],
        sample=[LogLine(**line) for line in summary["sample"]],
        truncated=summary["truncated"],
        note=note,
    )
