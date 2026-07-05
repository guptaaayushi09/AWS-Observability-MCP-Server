"""FastMCP server instance and tool registration.

Phase 0: a minimal server exposed over stdio with a single placeholder tool so the
transport, tool discovery, and MCP Inspector loop can be verified end to end before any
AWS logic is wired in.
"""

from __future__ import annotations

from datetime import datetime, timezone

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


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
def ping() -> dict[str, str]:
    """Health check for the server itself.

    Returns the server name, version, and current UTC time. Use this to confirm the MCP
    connection is live before calling the AWS tools.
    """
    return {
        "server": "aws-observability-mcp",
        "version": __version__,
        "utc_now": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
    }


def main() -> None:
    """Entry point: run the server over stdio (dev transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
