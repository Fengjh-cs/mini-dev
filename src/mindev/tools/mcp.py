"""Minimal MCP (Model Context Protocol) stdio client.

Speaks the MCP stdio transport (newline-delimited JSON-RPC 2.0) directly, so
mini-dev can load tools from any stdio MCP server (e.g. the official
filesystem / git servers launched via ``npx`` or ``uvx``).
"""

import json
import subprocess

from .base import Tool

_PROTOCOL_VERSION = "2024-11-05"


def format_mcp_result(result: dict) -> str:
    parts: list[str] = []
    for block in result.get("content", []):
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
        else:
            parts.append(json.dumps(block))
    text = "\n".join(parts)
    if result.get("isError"):
        text = "Error: " + text
    return text or "(no output)"


class McpClient:
    """Synchronous client for a single MCP stdio server."""

    def __init__(self, command: str, args: list[str] | None = None) -> None:
        self._proc = subprocess.Popen(
            [command, *(args or [])],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self._next_id = 1
        self._request(
            "initialize",
            {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "mini-dev", "version": "0.1.0"},
            },
        )
        self._notify("notifications/initialized")

    def _send(self, message: dict) -> None:
        self._proc.stdin.write(json.dumps(message) + "\n")
        self._proc.stdin.flush()

    def _request(self, method: str, params: dict | None = None) -> dict:
        self._send(
            {
                "jsonrpc": "2.0",
                "id": self._next_id,
                "method": method,
                "params": params or {},
            }
        )
        self._next_id += 1
        line = self._proc.stdout.readline()
        if not line:
            raise RuntimeError(f"MCP server closed stdout during '{method}'")
        return json.loads(line)

    def _notify(self, method: str, params: dict | None = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def list_tools(self) -> list[dict]:
        resp = self._request("tools/list")
        return resp.get("result", {}).get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> dict:
        resp = self._request("tools/call", {"name": name, "arguments": arguments})
        return resp.get("result", {})

    def close(self) -> None:
        try:
            self._proc.stdin.close()
        except Exception:
            pass
        self._proc.terminate()
        try:
            self._proc.wait(timeout=5)
        except Exception:
            self._proc.kill()


class McpTool(Tool):
    """Adapts an MCP tool definition into a mini-dev Tool."""

    def __init__(self, client: McpClient, tool_def: dict) -> None:
        self.name = tool_def["name"]
        self.description = tool_def.get("description", "")
        self.risk = "command"  # external tool of unknown safety: requires approval
        self._input_schema = tool_def.get(
            "inputSchema", {"type": "object", "properties": {}}
        )
        self._client = client

    def parameters(self) -> dict:
        return self._input_schema

    def run(self, arguments: dict) -> str:
        return format_mcp_result(self._client.call_tool(self.name, arguments))
