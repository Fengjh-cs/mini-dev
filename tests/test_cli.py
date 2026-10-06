from mindev.cli import main


def test_cli_prints_help(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "mini-dev" in out


def test_run_without_command_tool(monkeypatch, capsys, tmp_path):
    import dotenv
    import mindev.agent.loop
    import mindev.llm.openai
    from mindev.agent.trace import TraceEvent

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.chdir(tmp_path)
    original = tmp_path / "a.txt"
    original.write_text("original", encoding="utf-8")
    (tmp_path / ".env").write_text("synthetic-secret", encoding="utf-8")
    workspace = tmp_path.parent / f"{tmp_path.name}-isolated"
    seen = {}

    class FakeProvider:
        def __init__(self, **kwargs):
            pass

    class FakeLoop:
        def __init__(self, provider, tools, **kwargs):
            self.recorder = kwargs["recorder"]
            seen["tools"] = [schema["function"]["name"] for schema in tools.schemas()]
            seen["outside"] = tools.run("write_file", {
                "path": str(original), "content": "escaped",
            })
            seen["inside"] = tools.run("write_file", {
                "path": "a.txt", "content": "changed",
            })
            seen["env"] = tools.run("read_file", {"path": ".env"})

        def run(self, task):
            self.recorder.record(TraceEvent("tool_call", "write_file", 1, 0))
            return "done"

    monkeypatch.setattr(mindev.llm.openai, "OpenAIProvider", FakeProvider)
    monkeypatch.setattr(mindev.agent.loop, "AgentLoop", FakeLoop)
    assert main(["run", "--yes", "--no-repomap", "--no-bash",
                 "--output-dir", str(workspace), "--trace", "trace.jsonl", "task"]) == 0
    assert "bash" not in seen["tools"]
    assert "read_file" in seen["tools"]
    assert "write_file" in seen["tools"]
    assert seen["outside"].startswith("Error: access denied")
    assert seen["inside"].startswith("Wrote")
    assert seen["env"].startswith("Error: access denied")
    assert original.read_text(encoding="utf-8") == "original"
    assert (workspace / "a.txt").read_text(encoding="utf-8") == "changed"
    assert not (workspace / ".env").exists()
    assert (workspace / "trace.jsonl").exists()
    assert not (tmp_path / "trace.jsonl").exists()
    assert "done" in capsys.readouterr().out


def test_cli_rejects_local_bash_and_host_mcp(monkeypatch, capsys, tmp_path):
    import dotenv
    import mindev.cli

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.chdir(tmp_path)

    assert main(["run", "--sandbox", "local", "task"]) == 2
    assert "bash and --verify require --sandbox docker" in capsys.readouterr().err
    assert main(["run", "--sandbox", "local", "--no-bash", "--verify",
                 "python -m pytest -q", "task"]) == 2
    assert "bash and --verify require --sandbox docker" in capsys.readouterr().err
    assert main(["run", "--no-bash", "--mcp", "server", "task"]) == 2
    assert "host MCP servers" in capsys.readouterr().err
    assert main(["run", "--no-bash", "--checkpoint", "task"]) == 2
    assert "--checkpoint is unavailable" in capsys.readouterr().err
    assert main(["run", "--plan", "--verify", "python -m pytest -q", "task"]) == 2
    assert "read-only plan mode" in capsys.readouterr().err
    monkeypatch.setattr(mindev.cli.shutil, "which", lambda name: None)
    assert main(["run", "--no-bash", "--verify", "python -m pytest -q", "task"]) == 2
    assert "Docker is required" in capsys.readouterr().err


def test_cli_mounts_the_copy_for_docker_bash(monkeypatch, tmp_path):
    import dotenv
    import mindev.agent.loop
    import mindev.cli
    import mindev.llm.openai

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mindev.cli.shutil, "which", lambda name: "docker")
    workspace = tmp_path.parent / f"{tmp_path.name}-isolated"
    seen = {}

    class FakeProvider:
        def __init__(self, **kwargs):
            pass

    class FakeLoop:
        def __init__(self, provider, tools, **kwargs):
            seen["command"] = tools._tools["bash"]._sandbox.build_command("pwd")
            seen["read_root"] = tools._tools["read_file"]._access.root
            seen["write_root"] = tools._tools["write_file"]._access.root

        def run(self, task):
            return "done"

    monkeypatch.setattr(mindev.llm.openai, "OpenAIProvider", FakeProvider)
    monkeypatch.setattr(mindev.agent.loop, "AgentLoop", FakeLoop)
    assert main(["run", "--yes", "--no-repomap", "--output-dir", str(workspace), "task"]) == 0
    mount = seen["command"][seen["command"].index("--mount") + 1]
    assert mount == f"type=bind,source={workspace},target=/workspace"
    assert seen["read_root"] == workspace
    assert seen["write_root"] == workspace


def test_cli_verifier_uses_same_copy_without_exposing_bash(monkeypatch, tmp_path):
    import dotenv
    import mindev.agent.loop
    import mindev.cli
    import mindev.llm.openai

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mindev.cli.shutil, "which", lambda name: "docker")
    workspace = tmp_path.parent / f"{tmp_path.name}-verify"
    seen = {}

    class FakeProvider:
        def __init__(self, **kwargs):
            pass

    class FakeLoop:
        def __init__(self, provider, tools, **kwargs):
            seen["tools"] = [schema["function"]["name"] for schema in tools.schemas()]
            seen["verifier"] = kwargs["verifier"]
            seen["read_root"] = tools._tools["read_file"]._access.root

        def run(self, task):
            return "done"

    monkeypatch.setattr(mindev.llm.openai, "OpenAIProvider", FakeProvider)
    monkeypatch.setattr(mindev.agent.loop, "AgentLoop", FakeLoop)
    assert main(["run", "--no-bash", "--yes", "--no-repomap",
                 "--output-dir", str(workspace),
                 "--verify", "python -m pytest tests/test_tools.py -q", "task"]) == 0
    assert "bash" not in seen["tools"]
    assert seen["read_root"] == workspace
    assert seen["verifier"].commands == ("python -m pytest tests/test_tools.py -q",)
    command = seen["verifier"]._sandbox.build_command("python -m pytest tests/test_tools.py -q")
    assert f"type=bind,source={workspace},target=/workspace" in command
    assert "mindev-verify:local" in command
