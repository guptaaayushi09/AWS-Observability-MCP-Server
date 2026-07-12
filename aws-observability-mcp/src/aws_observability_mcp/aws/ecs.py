"""ECS service wrappers over boto3.

Thin functions that make the AWS call and return plain Python structures. No truncation or
MCP concerns live here so the layer can be unit-tested directly against moto.
"""

from __future__ import annotations

from typing import Any

from .clients import get_client


def describe_service(
    service_name: str,
    cluster: str | None = None,
    region: str | None = None,
) -> dict[str, Any] | None:
    """Fetch a single ECS service via DescribeServices.

    Returns the raw service dict (running/desired counts, deployments, events) or ``None``
    if no service by that name exists in the cluster.
    """
    client = get_client("ecs", region)
    kwargs: dict[str, Any] = {"services": [service_name]}
    if cluster:
        kwargs["cluster"] = cluster
    resp = client.describe_services(**kwargs)

    services = resp.get("services", [])
    return services[0] if services else None
