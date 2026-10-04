"""OpenAI provider built on the Responses API."""

import json
import os
from typing import Any

from openai import OpenAI

from .base import LLMProvider, ToolCall, Turn

DEFAULT_MODEL = "gpt-5-codex"
DEFAULT_SYSTEM = (
    "You are mini-dev, a coding agent. Complete the user's task by using the "
    "available tools to read files and run commands, then summarize what you "
    "found or did. Use tools to gather real information instead of guessing."
)


def _extract_text(item: Any) -> str:
    parts: list[str] = []
    for block in getattr(item, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts)


class OpenAIProvider(LLMProvider):
    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        system: str | None = None,
    ) -> None:
        self.model = model or os.getenv("MINIDEV_MODEL", DEFAULT_MODEL)
        self._client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self._system = system or DEFAULT_SYSTEM
        self._input: list[Any] = []

    def add_user(self, content: str) -> None:
        self._input.append({"role": "user", "content": content})

    def send(self, tools: list[dict]) -> Turn:
        response = self._client.responses.create(
            model=self.model,
            input=self._input,
            tools=tools,
            instructions=self._system,
        )
        # Keep the model's output in history verbatim (the documented pattern).
        self._input.extend(response.output)

        text = ""
        tool_calls: list[ToolCall] = []
        for item in response.output:
            if item.type == "message":
                text += _extract_text(item)
            elif item.type == "function_call":
                try:
                    arguments = json.loads(item.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {"_raw": item.arguments}
                tool_calls.append(
                    ToolCall(id=item.call_id, name=item.name, arguments=arguments)
                )
        return Turn(text=text, tool_calls=tool_calls)

    def add_tool_result(self, call_id: str, output: str) -> None:
        self._input.append(
            {"type": "function_call_output", "call_id": call_id, "output": output}
        )
