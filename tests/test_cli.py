from mindev.cli import main


def test_cli_prints_help(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "mini-dev" in out


def test_run_without_command_tool(monkeypatch, capsys):
    import dotenv
    import mindev.agent.loop
    import mindev.llm.openai

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    seen = {}

    class FakeProvider:
        def __init__(self, **kwargs):
            pass

    class FakeLoop:
        def __init__(self, provider, tools, **kwargs):
            seen["tools"] = [schema["function"]["name"] for schema in tools.schemas()]

        def run(self, task):
            return "done"

    monkeypatch.setattr(mindev.llm.openai, "OpenAIProvider", FakeProvider)
    monkeypatch.setattr(mindev.agent.loop, "AgentLoop", FakeLoop)
    assert main(["run", "--yes", "--no-repomap", "--no-bash", "task"]) == 0
    assert "bash" not in seen["tools"]
    assert "read_file" in seen["tools"]
    assert "write_file" in seen["tools"]
    assert "done" in capsys.readouterr().out
