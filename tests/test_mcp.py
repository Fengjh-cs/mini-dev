import sys
import textwrap

from mindev.tools.mcp import McpClient, McpTool, format_mcp_result

# A tiny MCP stdio server used as a test fixture. Speaks the same
# newline-delimited JSON-RPC the client expects.
SERVER_SCRIPT = textwrap.dedent(
    '''
    import json, sys

    def respond(msg_id, result):
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": result}) + "\\n")
        sys.stdout.flush()

    for line in sys.stdin:
        msg = json.loads(line)
        method = msg.get("method")
        if method == "initialize":
            respond(msg["id"], {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "test", "version": "1"}})
        elif method == "notifications/initialized":
            pass
        elif method == "tools/list":
            respond(msg["id"], {"tools": [{"name": "echo", "description": "echo text", "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}]})
        elif method == "tools/call":
            args = msg["params"]["arguments"]
            respond(msg["id"], {"content": [{"type": "text", "text": "echo:" + args.get("text", "")}]})
    '''
)


def _client() -> McpClient:
    return McpClient(command=sys.executable, args=["-c", SERVER_SCRIPT])


def test_mcp_list_tools():
    client = _client()
    try:
        tools = client.list_tools()
        assert tools[0]["name"] == "echo"
    finally:
        client.close()


def test_mcp_call_tool():
    client = _client()
    try:
        result = client.call_tool("echo", {"text": "hi"})
        assert format_mcp_result(result) == "echo:hi"
    finally:
        client.close()


def test_mcp_tool_adapter():
    client = _client()
    try:
        tool_def = client.list_tools()[0]
        tool = McpTool(client, tool_def)
        assert tool.name == "echo"
        assert tool.schema()["function"]["parameters"] == tool_def["inputSchema"]
        assert tool.risk == "command"
        assert "echo:hello" in tool.run({"text": "hello"})
    finally:
        client.close()
