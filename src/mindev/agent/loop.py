"""The core agent loop.

Ask the model, run any tools it requests (subject to the permission policy),
feed results back, repeat until the model answers without a tool call.
"""

from collections.abc import Callable

from ..llm.base import LLMProvider, ToolCall
from ..tools.registry import ToolRegistry
from .permissions import PermissionPolicy

Observer = Callable[[ToolCall], None]


class AgentLoop:
    def __init__(
        self,
        provider: LLMProvider,
        tools: ToolRegistry,
        max_iterations: int = 30,
        observer: Observer | None = None,
        policy: PermissionPolicy | None = None,
        compact_threshold: int | None = None,
        compact_keep: int = 6,
    ) -> None:
        self._provider = provider
        self._tools = tools
        self._max_iterations = max_iterations
        self._observer = observer
        self._policy = policy or PermissionPolicy()
        self._compact_threshold = compact_threshold
        self._compact_keep = compact_keep

    def run(self, task: str) -> str:
        self._provider.add_user(task)
        for _ in range(self._max_iterations):
            if (
                self._compact_threshold is not None
                and self._provider.context_tokens() > self._compact_threshold
            ):
                self._provider.compact(self._compact_keep)
            turn = self._provider.send(self._tools.schemas())
            if not turn.tool_calls:
                return turn.text.strip() or "(no response)"
            for call in turn.tool_calls:
                if self._policy.allow(call.name, self._tools.risk(call.name), call.arguments):
                    if self._observer:
                        self._observer(call)
                    output = self._tools.run(call.name, call.arguments)
                else:
                    output = f"DENIED: tool '{call.name}' was not approved."
                self._provider.add_tool_result(call.id, output)
        return "(reached the iteration limit before the task finished)"
