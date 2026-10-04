"""Delegate read-only exploration to a subagent."""

from ..agent.subagent import ExploreSubagent
from .base import Tool


class ExploreTool(Tool):
    name = "explore"
    description = (
        "Delegate a focused read-only exploration of the repository to a "
        "subagent with its own context. Returns a concise summary."
    )
    risk = "read"

    def __init__(self, subagent: ExploreSubagent) -> None:
        self._subagent = subagent

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to investigate."},
            },
            "required": ["query"],
        }

    def run(self, arguments: dict) -> str:
        return self._subagent.run(arguments.get("query", ""))
