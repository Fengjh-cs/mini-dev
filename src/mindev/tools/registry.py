"""Registry of tools the agent can call."""

from .base import Tool


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self._tools: dict[str, Tool] = {tool.name: tool for tool in tools}

    def schemas(self) -> list[dict]:
        return [tool.schema() for tool in self._tools.values()]

    def risk(self, name: str) -> str:
        tool = self._tools.get(name)
        return tool.risk if tool else "read"

    def run(self, name: str, arguments: dict) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"Error: unknown tool '{name}'."
        try:
            return tool.run(arguments)
        except Exception as exc:  # a tool must never crash the loop
            return f"Error: tool '{name}' raised: {exc}"
