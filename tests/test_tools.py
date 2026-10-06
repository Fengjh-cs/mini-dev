from mindev.tools.access import WorkspacePathPolicy
from mindev.tools.bash import BashTool
from mindev.tools.read import ReadTool
from mindev.tools.registry import ToolRegistry
from mindev.sandbox.local import LocalSandbox


def test_read_tool_returns_numbered_lines(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("line1\nline2\n")
    out = ReadTool(WorkspacePathPolicy(tmp_path)).run({"path": str(f)})
    assert "line1" in out and "line2" in out
    assert out.startswith("   1 ")


def test_read_tool_missing_file(tmp_path):
    out = ReadTool(WorkspacePathPolicy(tmp_path)).run({"path": str(tmp_path / "missing.txt")})
    assert out.startswith("Error: file not found")


def test_bash_tool_runs_echo():
    out = BashTool(LocalSandbox()).run({"command": "echo hello"})
    assert "hello" in out


def test_registry_schemas_and_run():
    reg = ToolRegistry([ReadTool(), BashTool(LocalSandbox())])
    schemas = reg.schemas()
    names = [s["function"]["name"] for s in schemas]
    assert names == ["read_file", "bash"]
    assert all(s["type"] == "function" for s in schemas)
    assert schemas[0]["function"]["parameters"]["required"] == ["path"]
    assert "unknown tool" in reg.run("nope", {})


def test_registry_catches_tool_exception():
    class Boom(ReadTool):
        name = "boom"

        def run(self, arguments: dict) -> str:
            raise RuntimeError("kaboom")

    reg = ToolRegistry([Boom()])
    out = reg.run("boom", {"path": "x"})
    assert out.startswith("Error")
    assert "kaboom" in out
