from mindev.agent.loop import AgentLoop
from mindev.agent.permissions import Mode, PermissionPolicy
from mindev.llm.base import LLMProvider, ToolCall, Turn
from mindev.tools.edit import WriteFileTool
from mindev.tools.registry import ToolRegistry


class ScriptedProvider(LLMProvider):
    def __init__(self, turns):
        self._turns = turns
        self._i = 0
        self.results = []

    def add_user(self, content):
        pass

    def send(self, tools):
        turn = self._turns[self._i]
        self._i += 1
        return turn

    def add_tool_result(self, call_id, output):
        self.results.append((call_id, output))


def test_policy_read_always_allowed():
    p = PermissionPolicy(mode=Mode.READONLY)
    assert p.allow("read_file", "read", {}) is True


def test_policy_write_denied_in_readonly():
    p = PermissionPolicy(mode=Mode.READONLY)
    assert p.allow("write_file", "write", {}) is False
    assert p.allow("bash", "command", {}) is False


def test_policy_write_allowed_without_approver():
    p = PermissionPolicy(mode=Mode.READWRITE)
    assert p.allow("bash", "command", {}) is True


def test_policy_write_asks_approver():
    p = PermissionPolicy(mode=Mode.READWRITE, approver=lambda name, args: name == "bash")
    assert p.allow("bash", "command", {}) is True
    assert p.allow("write_file", "write", {}) is False


def test_loop_readonly_policy_denies_registered_write(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("original")
    turns = [
        Turn("", [ToolCall("c1", "write_file", {"path": str(f), "content": "x"})]),
        Turn("ok", []),
    ]
    provider = ScriptedProvider(turns)
    loop = AgentLoop(
        provider,
        ToolRegistry([WriteFileTool()]),
        policy=PermissionPolicy(mode=Mode.READONLY),
    )
    loop.run("plan")
    assert provider.results[0][1].startswith("DENIED")
    assert f.read_text() == "original"


def test_loop_approver_can_deny(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("original")
    turns = [
        Turn("", [ToolCall("c1", "write_file", {"path": str(f), "content": "x"})]),
        Turn("ok", []),
    ]
    provider = ScriptedProvider(turns)
    policy = PermissionPolicy(mode=Mode.READWRITE, approver=lambda name, args: False)
    loop = AgentLoop(provider, ToolRegistry([WriteFileTool()]), policy=policy)
    loop.run("do it")
    assert "DENIED" in provider.results[0][1]
    assert f.read_text() == "original"


def test_loop_approver_can_allow(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("original")
    turns = [
        Turn("", [ToolCall("c1", "write_file", {"path": str(f), "content": "changed"})]),
        Turn("done", []),
    ]
    provider = ScriptedProvider(turns)
    policy = PermissionPolicy(mode=Mode.READWRITE, approver=lambda name, args: True)
    loop = AgentLoop(provider, ToolRegistry([WriteFileTool()]), policy=policy)
    loop.run("do it")
    assert f.read_text() == "changed"
