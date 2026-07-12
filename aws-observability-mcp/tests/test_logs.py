"""Tests for the tail_logs tool against moto-mocked CloudWatch Logs."""

from __future__ import annotations

from aws_observability_mcp.tools.logs import tail_logs

from conftest import seed_logs

LOG_GROUP = "/ecs/checkout-service"


def test_groups_similar_errors(aws):
    messages = [
        "ERROR connection refused to db host 10.0.0.1",
        "ERROR connection refused to db host 10.0.0.2",
        "ERROR connection refused to db host 10.0.0.3",
        "WARN cache miss for key abc",
    ]
    start, end = seed_logs(LOG_GROUP, messages)

    result = tail_logs(log_group=LOG_GROUP, start_time=start, end_time=end)

    assert result.event_count == 4
    # The three connection-refused lines collapse into one pattern with count 3.
    top = result.error_patterns[0]
    assert top.count == 3
    assert "connection refused" in top.pattern
    assert result.note is None


def test_sample_truncates_and_marks_truncated(aws):
    messages = [f"ERROR request {i} failed" for i in range(30)]
    start, end = seed_logs(LOG_GROUP, messages)

    result = tail_logs(log_group=LOG_GROUP, start_time=start, end_time=end, limit=30)

    assert result.event_count == 30
    assert result.truncated is True
    assert len(result.sample) == 20
    # All 30 lines share one masked template.
    assert result.error_patterns[0].count == 30


def test_filter_pattern_narrows_results(aws):
    messages = ["ERROR boom", "INFO all good", "ERROR boom again"]
    start, end = seed_logs(LOG_GROUP, messages)

    result = tail_logs(
        log_group=LOG_GROUP,
        start_time=start,
        end_time=end,
        filter_pattern="ERROR",
    )

    assert result.event_count == 2
    assert all("ERROR" in line.message for line in result.sample)


def test_no_events_returns_note(aws):
    start, end = seed_logs(LOG_GROUP, ["ERROR one"])

    result = tail_logs(
        log_group=LOG_GROUP,
        start_time=start,
        end_time=end,
        filter_pattern="NOTHINGMATCHESTHIS",
    )

    assert result.event_count == 0
    assert result.note is not None
