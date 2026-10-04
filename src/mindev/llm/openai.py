"""OpenAI-compatible provider built on the Chat Completions API.

We use Chat Completions (not the Responses API) so the same provider works with
any OpenAI-compatible backend — OpenAI, DeepSeek, OpenRouter, etc. — simply by
setting ``OPENAI_BASE_URL`` (or passing ``base_url=``).
"""

import json
import os

from openai import OpenAI

from .base import LLMProvider, ToolCall, Turn

DEFAULT_MODEL = "gpt-5-mini"
DEFAULT_SYSTEM = (
    "You are mini-dev, a coding agent. Complete the user's task by using the "
    "available tools to read files and run commands, then summarize what you "
    "found or did. Use tools to gather real information instead of guessing."
)


class OpenAIProvider(LLMProvider):
    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        system: str | None = None,
    ) -> None:
        self.model = model or os.getenv("MINIDEV_MODEL", DEFAULT_MODEL)
        self._client = OpenAI(
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            base_url=base_url or os.getenv("OPENAI_BASE_URL") or None,
        )
        system = system if system is not None else DEFAULT_SYSTEM
        self._messages: list[dict] = []
        if system:
            self._messages.append({"role": "system", "content": system})

    def add_user(self, content: str) -> None:
        self._messages.append({"role": "user", "content": content})

    def send(self, tools: list[dict]) -> Turn:
        kwargs: dict = {"model": self.model, "messages": self._messages}
        if tools:
            kwargs["tools"] = tools
        response = self._client.chat.completions.create(**kwargs)
        message = response.choices[0].message

        assistant: dict = {"role": "assistant", "content": message.content or ""}
        if message.tool_calls:
            assistant["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ]
        self._messages.append(assistant)

        tool_calls: list[ToolCall] = []
        for tc in message.tool_calls or []:
            try:
                arguments = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {"_raw": tc.function.arguments}
            tool_calls.append(
                ToolCall(id=tc.id, name=tc.function.name, arguments=arguments)
            )
        return Turn(text=message.content or "", tool_calls=tool_calls)

    def add_tool_result(self, call_id: str, output: str) -> None:
        self._messages.append(
            {"role": "tool", "tool_call_id": call_id, "content": output}
        )
