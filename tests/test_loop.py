from mindev.agent.loop import AgentLoop
from mindev.llm.base import LLMProvider, ToolCall, Turn
from mindev.tools.read import ReadTool
from mindev.tools.registry import ToolRegistry


class ScriptedProvider(LLMProvider):
    """Fake provider that returns a pre-scripted sequence of turns."""

    def __init__(self, turns: list[Turn]) -> None:
        self._turns = turns
        self._i = 0
        self.users: list[str] = []
        self.tool_results: list[tuple[str, str]] = []

    def add_user(self, content: str) -> None:
        self.users.append(content)

    def send(self, tools: list[dict]) -> Turn:
        turn = self._turns[self._i]
        self._i += 1
        return turn

    def add_tool_result(self, call_id: str, output: str) -> None:
        self.tool_results.append((call_id, output))


def test_loop_runs_tool_and_returns_final_text(tmp_path):
    f = tmp_path / "hello.txt"
    f.write_text("hi\n")

    turns = [
        Turn(text="", tool_calls=[ToolCall("c1", "read_file", {"path": str(f)})]),
        Turn(text="The file says hi.", tool_calls=[]),
    ]
    provider = ScriptedProvider(turns)
    loop = AgentLoop(provider, ToolRegistry([ReadTool()]))

    result = loop.run("read that file")

    assert result == "The file says hi."
    assert provider.users == ["read that file"]
    assert provider.tool_results[0][0] == "c1"
    assert "hi" in provider.tool_results[0][1]


def test_loop_feeds_back_unknown_tool_error():
    turns = [
        Turn(text="", tool_calls=[ToolCall("c1", "does_not_exist", {})]),
        Turn(text="done", tool_calls=[]),
    ]
    provider = ScriptedProvider(turns)
    loop = AgentLoop(provider, ToolRegistry([ReadTool()]))

    loop.run("x")

    assert "unknown tool" in provider.tool_results[0][1]


def test_loop_stops_at_iteration_limit():
    turn = Turn(text="", tool_calls=[ToolCall("c1", "read_file", {"path": "x"})])
    provider = ScriptedProvider([turn] * 10)
    loop = AgentLoop(provider, ToolRegistry([ReadTool()]), max_iterations=3)

    result = loop.run("x")

    assert "iteration limit" in result
