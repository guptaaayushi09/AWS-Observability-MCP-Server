"""Tests for the get_service_health tool against moto-mocked ECS."""

from __future__ import annotations

from aws_observability_mcp.tools.health import get_service_health

from conftest import seed_ecs_service


def test_reports_healthy_service(aws):
    cluster = seed_ecs_service("checkout-service", desired_count=3)

    result = get_service_health("checkout-service", cluster=cluster)

    assert result.service_name == "checkout-service"
    assert result.status == "ACTIVE"
    assert result.desired_count == 3
    assert result.deploying is False
    assert len(result.deployments) == 1
    assert result.note is None


def test_missing_service_returns_note(aws):
    seed_ecs_service("checkout-service")

    result = get_service_health("does-not-exist", cluster="test-cluster")

    assert result.desired_count is None
    assert result.deployments == []
    assert result.note is not None
    assert "does-not-exist" in result.note
