"""A bounded, read-only exploration subagent with its own context window."""

from ..tools.registry import ToolRegistry
from .loop import AgentLoop
from .permissions import Mode, PermissionPolicy

EXPLORE_INSTRUCTIONS = (
    "You are a read-only exploration subagent. Investigate the repository to "
    "answer the given question using read_file, then return a concise summary."
)


class ExploreSubagent:
    def __init__(
        self,
        provider_factory,
        tools: ToolRegistry,
        max_iterations: int = 10,
    ) -> None:
        self._factory = provider_factory
        self._tools = tools
        self._max_iterations = max_iterations

    def run(self, query: str) -> str:
        # A fresh provider each run => isolated context window; only the
        # summary comes back, not the full transcript.
        provider = self._factory()
        loop = AgentLoop(
            provider,
            self._tools,
            max_iterations=self._max_iterations,
            policy=PermissionPolicy(mode=Mode.READONLY),
        )
        return loop.run(query)
