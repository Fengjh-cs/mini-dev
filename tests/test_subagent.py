from mindev.agent.subagent import ExploreSubagent
from mindev.llm.base import LLMProvider, Turn
from mindev.tools.explore import ExploreTool
from mindev.tools.read import ReadTool
from mindev.tools.registry import ToolRegistry


class P(LLMProvider):
    def __init__(self, text):
        self._text = text

    def add_user(self, content):
        pass

    def send(self, tools):
        return Turn(self._text, [])

    def add_tool_result(self, call_id, output):
        pass


def test_explore_tool_delegates_and_returns_summary():
    sub = ExploreSubagent(lambda: P("found foo() in bar.py"), ToolRegistry([ReadTool()]))
    tool = ExploreTool(sub)
    out = tool.run({"query": "where is foo"})
    assert "foo()" in out


def test_subagent_creates_fresh_provider_each_run():
    calls = []

    class Counter(P):
        def __init__(self):
            super().__init__("ok")
            calls.append(1)

    sub = ExploreSubagent(lambda: Counter(), ToolRegistry([ReadTool()]))
    sub.run("q1")
    sub.run("q2")
    assert len(calls) == 2  # isolated context: a fresh provider per run
