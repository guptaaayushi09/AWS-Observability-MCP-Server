"""Server entry point.

Imports the shared FastMCP instance, pulls in the tool modules so their `@mcp.tool`
registrations run, and exposes `main()` to serve over stdio (dev transport).
"""

from __future__ import annotations

from datetime import datetime, timezone

from . import __version__
from .app import READ_ONLY, mcp

# Importing the tool modules registers their tools on `mcp` as a side effect.
from .tools import alarms as _alarms  # noqa: F401
from .tools import health as _health  # noqa: F401
from .tools import logs as _logs  # noqa: F401
from .tools import metrics as _metrics  # noqa: F401


@mcp.tool(annotations=READ_ONLY)
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
    """Run the server over stdio (dev transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
