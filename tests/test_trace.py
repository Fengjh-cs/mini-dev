from mindev.agent.loop import AgentLoop
from mindev.agent.trace import TraceRecorder
from mindev.llm.base import LLMProvider, ToolCall, Turn
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

    def context_tokens(self):
        return 100


def test_recorder_records_tool_calls():
    turns = [
        Turn("", [ToolCall("c1", "read_file", {"path": "missing.txt"})]),
        Turn("done", []),
    ]
    rec = TraceRecorder()
    AgentLoop(ScriptedProvider(turns), ToolRegistry([ReadTool()]), recorder=rec).run("task")
    assert rec.summarize()["tool_calls"] == 1
    assert rec.events[0].kind == "tool_call"
    assert rec.events[0].name == "read_file"


def test_recorder_writes_jsonl(tmp_path):
    path = str(tmp_path / "trace.jsonl")
    turns = [Turn("", [ToolCall("c1", "read_file", {"path": "x"})]), Turn("done", [])]
    rec = TraceRecorder(path)
    AgentLoop(ScriptedProvider(turns), ToolRegistry([ReadTool()]), recorder=rec).run("task")
    lines = open(path).read().strip().splitlines()
    assert len(lines) == 1
    assert '"tool_call"' in lines[0]


def test_recorder_records_compact():
    class FakeProvider(LLMProvider):
        def __init__(self):
            self._tokens = 1000

        def add_user(self, content):
            self._tokens += 100

        def send(self, tools):
            self._tokens += 500
            return Turn("done", [])

        def add_tool_result(self, call_id, output):
            self._tokens += 200

        def context_tokens(self):
            return self._tokens

        def compact(self, keep_messages=6):
            self._tokens = 50
            return "summary"

    rec = TraceRecorder()
    AgentLoop(
        FakeProvider(), ToolRegistry([ReadTool()]), recorder=rec, compact_threshold=500
    ).run("task")
    assert "compact" in [e.kind for e in rec.events]
