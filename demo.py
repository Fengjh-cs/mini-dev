"""Run mini-dev without an API key: RepoMap + a deterministic agent run.

Usage:
    python demo.py
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from mindev.agent.loop import AgentLoop
from mindev.context.repomap import RepoMap
from mindev.llm.base import LLMProvider, ToolCall, Turn
from mindev.tools.bash import BashTool
from mindev.tools.edit import EditFileTool, WriteFileTool
from mindev.tools.read import ReadTool
from mindev.tools.registry import ToolRegistry


class ScriptedProvider(LLMProvider):
    def __init__(self, turns):
        self._turns = turns
        self._i = 0

    def add_user(self, content):
        pass

    def send(self, tools):
        turn = self._turns[self._i]
        self._i += 1
        return turn

    def add_tool_result(self, call_id, output):
        pass


def _observer(call):
    args = ", ".join(f"{k}={v!r}" for k, v in call.arguments.items())
    print(f"  -> {call.name}({args})")


def main() -> int:
    print("=" * 60)
    print("mini-dev demo (no API key needed)")
    print("=" * 60)

    print("\n[1] RepoMap - tree-sitter symbol index of this repo\n")
    print(RepoMap(max_tokens=1200).build("."))

    print("\n[2] Agent loop - scripted provider (deterministic)\n")
    turns = [
        Turn("", [ToolCall("c1", "write_file", {"path": "greeting.txt", "content": "hello"})]),
        Turn("", [ToolCall("c2", "edit_file", {"path": "greeting.txt", "old_string": "hello", "new_string": "hello world"})]),
        Turn("", [ToolCall("c3", "bash", {"command": "echo hello"})]),
        Turn("Done: wrote greeting.txt, edited it, and ran a command.", []),
    ]
    original = os.getcwd()
    with tempfile.TemporaryDirectory() as d:
        os.chdir(d)
        try:
            tools = ToolRegistry([ReadTool(), WriteFileTool(), EditFileTool(), BashTool()])
            result = AgentLoop(ScriptedProvider(turns), tools, observer=_observer).run(
                "create and edit a greeting file"
            )
        finally:
            os.chdir(original)

    print(f"\nFinal answer: {result}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
