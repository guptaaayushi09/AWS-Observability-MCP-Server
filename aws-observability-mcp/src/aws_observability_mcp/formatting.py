"""Truncation and summarization helpers.

Every AWS payload passes through here before it is returned to the model. AWS APIs can
return enormous responses (a metric query can yield ~100k datapoints); returning them raw
would blow the context window and cost. These helpers pre-summarize instead.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

# Cap on how many raw items (datapoints, log lines) we ever hand back to the model.
DEFAULT_SAMPLE_SIZE = 20


def percentile(sorted_values: list[float], pct: float) -> float:
    """Return the ``pct`` percentile (0-100) of an already-sorted, non-empty list.

    Uses linear interpolation between closest ranks. Kept dependency-free on purpose.
    """
    if not sorted_values:
        raise ValueError("percentile() requires at least one value")
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (pct / 100) * (len(sorted_values) - 1)
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    frac = rank - low
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * frac


def summarize_series(
    values: list[float],
    sample_size: int = DEFAULT_SAMPLE_SIZE,
) -> dict[str, Any]:
    """Reduce a numeric time series to summary stats plus a truncated sample.

    Returns p50/p95/max/min/latest and the datapoint count, so the model gets the shape of
    the series without the full payload. ``latest`` assumes ``values`` is in chronological
    order (oldest first).
    """
    if not values:
        return {
            "datapoint_count": 0,
            "p50": None,
            "p95": None,
            "max": None,
            "min": None,
            "latest": None,
            "sample": [],
            "truncated": False,
        }

    ordered = sorted(values)
    truncated = len(values) > sample_size
    return {
        "datapoint_count": len(values),
        "p50": round(percentile(ordered, 50), 4),
        "p95": round(percentile(ordered, 95), 4),
        "max": ordered[-1],
        "min": ordered[0],
        "latest": values[-1],
        # Keep the most recent points — during an incident the tail matters most.
        "sample": values[-sample_size:],
        "truncated": truncated,
    }


# Volatile substrings that make otherwise-identical log lines look distinct. Replacing them
# with placeholders lets us collapse "user 5f3a timed out" and "user 91bc timed out" into one
# error pattern with a count.
_UUID = re.compile(r"\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b")
_HEX = re.compile(r"\b0x[0-9a-fA-F]+\b")
_LONGHEX = re.compile(r"\b[0-9a-fA-F]{16,}\b")
_TIMESTAMP = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b")
_NUMBER = re.compile(r"\b\d+\b")


def _error_template(message: str) -> str:
    """Normalize a log line into a template by masking volatile tokens.

    IDs, hex, timestamps, and bare numbers become placeholders so similar errors group.
    """
    text = message.strip()
    text = _TIMESTAMP.sub("<ts>", text)
    text = _UUID.sub("<id>", text)
    text = _HEX.sub("<hex>", text)
    text = _LONGHEX.sub("<hex>", text)
    text = _NUMBER.sub("<n>", text)
    return re.sub(r"\s+", " ", text)


def summarize_log_events(
    events: list[dict[str, Any]],
    sample_size: int = DEFAULT_SAMPLE_SIZE,
) -> dict[str, Any]:
    """Reduce raw log events to a sample of recent lines plus grouped error patterns.

    ``events`` are FilterLogEvents dicts (``timestamp`` epoch-millis, ``message``), assumed
    oldest-first. Returns the most recent ``sample_size`` lines and a count per normalized
    error template so the model sees "3× connection refused" instead of 3 raw lines.
    """
    if not events:
        return {
            "event_count": 0,
            "sample": [],
            "error_patterns": [],
            "truncated": False,
        }

    templates: Counter[str] = Counter()
    for event in events:
        templates[_error_template(event.get("message", ""))] += 1

    error_patterns = [
        {"pattern": pattern, "count": count}
        for pattern, count in templates.most_common()
    ]

    recent = events[-sample_size:]
    sample = [
        {"timestamp": e.get("timestamp"), "message": e.get("message", "").strip()}
        for e in recent
    ]

    return {
        "event_count": len(events),
        "sample": sample,
        "error_patterns": error_patterns,
        "truncated": len(events) > sample_size,
    }
