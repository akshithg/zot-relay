"""Prepare and verify a local Zot Relay installation for any stdio MCP client."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import sysconfig
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


def mcp_executable() -> Path:
    """Find the server in the same persistent environment as this setup helper."""
    name = "zot-relay-mcp.exe" if sys.platform == "win32" else "zot-relay-mcp"
    return Path(sysconfig.get_path("scripts")) / name


def bundled_bridge() -> tuple[Path, str]:
    plugin = Path(__file__).resolve().parent / "assets/zot-relay-bridge.xpi"
    with zipfile.ZipFile(plugin) as archive:
        version = json.loads(archive.read("manifest.json"))["version"]
    return plugin, version


def prepare_install() -> dict[str, Any]:
    """Describe the installed server and matching plugin without editing client settings."""
    executable = mcp_executable()
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise RuntimeError("The zot-relay-mcp program is missing or not executable. Reinstall the Zot Relay package.")
    plugin, version = bundled_bridge()
    return {
        "ok": True,
        "serverName": "zot-relay",
        "mcpServer": {"command": str(executable.resolve()), "args": []},
        "plugin": str(plugin),
        "pluginVersion": version,
    }


async def check_connection() -> dict[str, Any]:
    """Test the installed stdio server and matching bridge without library writes."""
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters
    from mcp.types import TextContent

    prepared = prepare_install()
    bundled = prepared["pluginVersion"]
    parameters = StdioServerParameters(command=prepared["mcpServer"]["command"])
    response = None
    async with Client(parameters, read_timeout_seconds=15) as client:
        tools = (await client.list_tools()).tools
        if [tool.name for tool in tools] == ["eval_zotero"]:
            response = await client.call_tool(
                "eval_zotero",
                {"code": "return JSON.stringify({ok: true, zoteroVersion: Zotero.version});", "timeout_seconds": 5},
            )
    # Raise after the SDK context closes so diagnostics are not hidden in a task-group error.
    if response is None:
        raise RuntimeError("Zot Relay's Zotero tool could not be found. Reinstall the Zot Relay package.")
    if response.is_error:
        message = " ".join(part.text for part in response.content if isinstance(part, TextContent))
        raise RuntimeError(message or "The Zotero connection check failed.")
    result = response.structured_content
    if not isinstance(result, dict) or result.get("ok") is not True or not result.get("zoteroVersion"):
        raise RuntimeError("Zotero returned an unexpected connection-check result.")
    with urllib.request.urlopen("http://127.0.0.1:24119/status", timeout=5) as status:
        installed = json.load(status).get("version")
    if installed != bundled:
        raise RuntimeError(
            f"The running Zotero bridge is {installed}; this package needs {bundled}. "
            "Install the plugin reported by zot-relay-setup prepare through Tools > Plugins and restart Zotero."
        )
    return {**result, "bridgeVersion": installed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare Zot Relay for an MCP agent. No library data is changed.")
    parser.add_argument("action", choices=["prepare", "check"])
    args = parser.parse_args(argv)
    try:
        result = prepare_install() if args.action == "prepare" else asyncio.run(check_connection())
        print(json.dumps(result))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
