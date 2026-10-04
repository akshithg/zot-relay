"""Expose Zotero JavaScript execution as one stdio MCP tool."""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING, Any

from zot_relay.bridge import BridgeError, execute_js

if TYPE_CHECKING:
    from mcp.server import MCPServer


def create_server() -> MCPServer:
    from mcp.server import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
    from mcp.types import ToolAnnotations

    server = MCPServer(
        "zot-relay",
        instructions=(
            "Execute caller-written JavaScript inside the user's running Zotero. "
            "Stay within the task the user authorized and back up affected data before bulk writes. "
            "A timeout does not cancel execution; check affected state before retrying."
        ),
        log_level="WARNING",
    )

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=True,
            idempotent_hint=False,
            open_world_hint=True,
        ),
    )
    def eval_zotero(code: str, timeout_seconds: float = 60.0) -> dict[str, Any]:
        """Evaluate JavaScript with Zotero's privileges, including library and file access.

        Send a bare async function body ending in return JSON.stringify(...).
        Await asynchronous Zotero APIs; do not wrap the body in another function.
        timeout_seconds limits the wait for a response, not JavaScript execution.
        """
        if not code.strip():
            raise ToolError("code must contain a JavaScript statement body")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ToolError("timeout_seconds must be finite and greater than zero")

        try:
            result = execute_js(code, timeout=timeout_seconds).get("result")
        except BridgeError as exc:
            raise ToolError(str(exc)) from exc
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                pass
        return result if isinstance(result, dict) else {"result": result}

    return server


def main() -> int:
    create_server().run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
