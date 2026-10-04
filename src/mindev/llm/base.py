"""Provider abstraction for LLM access.

Phase 1 keeps this intentionally small: a provider owns its own conversation
state and exposes the three methods the agent loop needs.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class Turn:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMProvider(ABC):
    @abstractmethod
    def add_user(self, content: str) -> None:
        """Append a user message to the conversation."""

    @abstractmethod
    def send(self, tools: list[dict]) -> Turn:
        """Call the model once with the given tool schemas."""

    @abstractmethod
    def add_tool_result(self, call_id: str, output: str) -> None:
        """Append a tool result to the conversation."""

    def context_tokens(self) -> int:
        """Estimated token count of the current context (0 = not tracked)."""
        return 0

    def compact(self, keep_messages: int = 6) -> str:
        """Summarize older messages, keeping the most recent ones.

        Returns the summary text, or "" if nothing was compacted. No-op by
        default; providers that track context override it.
        """
        return ""
