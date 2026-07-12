"""The `get_service_health` MCP tool.

Wraps ECS DescribeServices and reduces it to the "is this service healthy / mid-deploy?"
signals: running vs desired counts, rollout state, and the most recent service events.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..app import READ_ONLY, mcp
from ..aws.ecs import describe_service

# Cap on how many service events we hand back; ECS keeps a long history but only the tail
# is relevant during an incident.
_MAX_EVENTS = 10


class Deployment(BaseModel):
    """One ECS deployment (there are two while a rollout is in progress)."""

    status: str = Field(description="PRIMARY (target), ACTIVE (draining), or INACTIVE.")
    desired_count: int
    running_count: int
    pending_count: int
    rollout_state: str | None = Field(
        default=None, description="COMPLETED, IN_PROGRESS, or FAILED when available."
    )


class ServiceEvent(BaseModel):
    """A timestamped message from the ECS service event log."""

    created_at: str | None
    message: str


class ServiceHealth(BaseModel):
    """Summarized ECS service health."""

    service_name: str
    cluster: str | None
    status: str | None = Field(default=None, description="ACTIVE / DRAINING / INACTIVE.")
    desired_count: int | None
    running_count: int | None
    pending_count: int | None
    deploying: bool = Field(description="True if more than one deployment is active.")
    deployments: list[Deployment]
    recent_events: list[ServiceEvent]
    note: str | None = Field(default=None, description="Guidance when the service is missing.")


@mcp.tool(annotations=READ_ONLY)
def get_service_health(
    service_name: str,
    cluster: str | None = None,
) -> ServiceHealth:
    """Check whether an ECS service is healthy or mid-deployment.

    Returns running vs desired task counts, deployment rollout status, and the most recent
    service events. Use this first during an incident to rule out a bad deploy before
    digging into metrics and logs.

    Args:
        service_name: The ECS service name, e.g. "checkout-service".
        cluster: The ECS cluster name. Omit to use the default cluster.
    """
    service = describe_service(service_name=service_name, cluster=cluster)

    if service is None:
        return ServiceHealth(
            service_name=service_name,
            cluster=cluster,
            desired_count=None,
            running_count=None,
            pending_count=None,
            deploying=False,
            deployments=[],
            recent_events=[],
            note=(
                f"No ECS service named '{service_name}' found"
                + (f" in cluster '{cluster}'" if cluster else "")
                + ". Verify the service name and cluster."
            ),
        )

    deployments = [
        Deployment(
            status=d.get("status", "UNKNOWN"),
            desired_count=d.get("desiredCount", 0),
            running_count=d.get("runningCount", 0),
            pending_count=d.get("pendingCount", 0),
            rollout_state=d.get("rolloutState"),
        )
        for d in service.get("deployments", [])
    ]

    # ECS returns events newest-first; keep the newest handful.
    recent_events = [
        ServiceEvent(
            created_at=e["createdAt"].isoformat() if e.get("createdAt") else None,
            message=e.get("message", ""),
        )
        for e in service.get("events", [])[:_MAX_EVENTS]
    ]

    return ServiceHealth(
        service_name=service_name,
        cluster=cluster,
        status=service.get("status"),
        desired_count=service.get("desiredCount"),
        running_count=service.get("runningCount"),
        pending_count=service.get("pendingCount"),
        deploying=len(deployments) > 1,
        deployments=deployments,
        recent_events=recent_events,
    )
