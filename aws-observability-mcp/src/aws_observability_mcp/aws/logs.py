"""CloudWatch Logs wrappers over boto3.

Thin functions that make the AWS call and return plain Python structures. No truncation or
MCP concerns live here so the layer can be unit-tested directly against moto.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .clients import get_client


def _to_millis(when: datetime) -> int:
    """CloudWatch Logs expects epoch milliseconds for time bounds."""
    return int(when.timestamp() * 1000)


def filter_log_events(
    log_group: str,
    start_time: datetime,
    end_time: datetime,
    filter_pattern: str | None = None,
    limit: int = 50,
    region: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch matching log events via CloudWatch Logs FilterLogEvents.

    Returns event dicts (``timestamp`` in epoch millis, ``message``) oldest-first, capped at
    ``limit``. Pagination is followed only as far as needed to fill ``limit``.
    """
    client = get_client("logs", region)
    events: list[dict[str, Any]] = []
    next_token: str | None = None
    while len(events) < limit:
        kwargs: dict[str, Any] = {
            "logGroupName": log_group,
            "startTime": _to_millis(start_time),
            "endTime": _to_millis(end_time),
            "limit": limit - len(events),
        }
        if filter_pattern:
            kwargs["filterPattern"] = filter_pattern
        if next_token:
            kwargs["nextToken"] = next_token
        resp = client.filter_log_events(**kwargs)

        events.extend(resp.get("events", []))

        next_token = resp.get("nextToken")
        if not next_token:
            break

    events.sort(key=lambda e: e.get("timestamp", 0))
    return events[:limit]
