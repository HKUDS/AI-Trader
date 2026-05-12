"""External-service integrations for BW-Trader.

This package owns thin adapters around third-party agent infrastructure
that BW-Trader does not control (e.g. Pionex AI Kit MCP server). The
adapters do nothing that the no-auto-trade red line forbids on their
own — every write path defers to `security.assert_paper_only` before
touching the underlying transport.
"""

from .pionex_mcp_client import (
    PionexMCPClient,
    PionexMCPError,
    Transport,
)

__all__ = [
    "PionexMCPClient",
    "PionexMCPError",
    "Transport",
]
