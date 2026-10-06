from mindev.agent.loop import AgentLoop
from mindev.llm.base import LLMProvider, ToolCall, Turn
from mindev.tools.access import WorkspacePathPolicy
from mindev.tools.edit import WriteFileTool
from mindev.tools.read import ReadTool
from mindev.tools.registry import ToolRegistry


def test_validate_accepts_valid_args():
    assert ReadTool().validate({"path": "x"}) is None


def test_validate_rejects_missing_required():
    err = WriteFileTool().validate({"path": "a.txt"})  # missing content
    assert err is not None and "content" in err


def test_validate_rejects_wrong_type():
    err = WriteFileTool().validate({"path": "a.txt", "content": 123})
    assert err is not None


def test_validate_rejects_non_dict():
    assert ReadTool().validate(["not", "a", "dict"]) is not None


def test_registry_returns_structured_error_on_invalid_args():
    reg = ToolRegistry([WriteFileTool()])
    out = reg.run("write_file", {"path": "a.txt"})  # missing content
    assert out.startswith("Error")
    assert "invalid arguments" in out


def test_registry_does_not_call_run_on_invalid_args():
    calls = []

    class Counting(ReadTool):
        name = "counting"

        def run(self, arguments):
            calls.append(arguments)
            return "ok"

    reg = ToolRegistry([Counting()])
    out = reg.run("counting", {})  # missing required 'path'
    assert calls == []
    assert "invalid arguments" in out


def test_loop_feeds_validation_error_back_for_self_correction(tmp_path):
    out_path = str(tmp_path / "out.txt")
    turns = [
        Turn("", [ToolCall("c1", "write_file", {"path": out_path})]),  # missing content
        Turn("", [ToolCall("c2", "write_file", {"path": out_path, "content": "hi"})]),
        Turn("done", []),
    ]

    class Scripted(LLMProvider):
        def __init__(self):
            self._i = 0
            self.results = []

        def add_user(self, content):
            pass

        def send(self, tools):
            turn = turns[self._i]
            self._i += 1
            return turn

        def add_tool_result(self, call_id, output):
            self.results.append((call_id, output))

    provider = Scripted()
    loop = AgentLoop(provider, ToolRegistry([WriteFileTool(access=WorkspacePathPolicy(tmp_path))]))
    loop.run("create out.txt")

    assert "invalid arguments" in provider.results[0][1]
    assert (tmp_path / "out.txt").read_text() == "hi"
