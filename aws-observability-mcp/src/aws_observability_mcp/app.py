"""The shared FastMCP application instance.

Kept in its own module so tool modules can register against it without importing the
server entry point (which would create a circular import).
"""

from __future__ import annotations

from fastmcp import FastMCP

from . import __version__

mcp = FastMCP(
    name="aws-observability-mcp",
    version=__version__,
    instructions=(
        "Read-only AWS CloudWatch + ECS observability tools for natural-language incident "
        "investigation. Compose the tools per question: check service health, query metrics, "
        "tail logs, and list firing alarms, then correlate the results."
    ),
)

# Reusable annotations: every tool in this server is read-only and safe to retry.
READ_ONLY = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}
