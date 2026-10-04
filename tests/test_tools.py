from mindev.tools.bash import BashTool
from mindev.tools.read import ReadTool
from mindev.tools.registry import ToolRegistry


def test_read_tool_returns_numbered_lines(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("line1\nline2\n")
    out = ReadTool().run({"path": str(f)})
    assert "line1" in out and "line2" in out
    assert out.startswith("   1 ")


def test_read_tool_missing_file():
    out = ReadTool().run({"path": "/no/such/file.txt"})
    assert out.startswith("Error")


def test_bash_tool_runs_echo():
    out = BashTool().run({"command": "echo hello"})
    assert "hello" in out


def test_registry_schemas_and_run():
    reg = ToolRegistry([ReadTool(), BashTool()])
    names = [s["name"] for s in reg.schemas()]
    assert names == ["read_file", "bash"]
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
