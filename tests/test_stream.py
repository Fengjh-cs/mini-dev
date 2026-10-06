from types import SimpleNamespace

import mindev.llm.openai as oai
from mindev.llm.openai import OpenAIProvider
from mindev.tools.read import ReadTool
from mindev.tools.registry import ToolRegistry


def _chunk(content=None, tool_calls=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=tool_calls))]
    )


def _tc(index, id=None, name=None, args=None):
    return SimpleNamespace(
        index=index, id=id, function=SimpleNamespace(name=name, arguments=args)
    )


def test_stream_collects_tokens_and_tool_calls(monkeypatch):
    chunks = [
        _chunk(content="Hello "),
        _chunk(content="world"),
        _chunk(tool_calls=[_tc(0, id="c1", name="read_file", args='{"path":')]),
        _chunk(tool_calls=[_tc(0, args='"a.txt"}')]),
    ]
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: chunks))
    )
    monkeypatch.setattr(oai, "OpenAI", lambda **kw: fake_client)

    tokens = []
    provider = OpenAIProvider(api_key="sk-test", on_token=tokens.append)
    turn = provider.send([{"type": "function", "name": "read_file"}])

    assert tokens == ["Hello ", "world"]
    assert turn.text == "Hello world"
    assert turn.tool_calls[0].name == "read_file"
    assert turn.tool_calls[0].arguments == {"path": "a.txt"}
    assert provider._messages[-1]["tool_calls"][0]["id"] == "c1"


def test_no_stream_when_on_token_absent(monkeypatch):
    def create(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="done", tool_calls=None))]
        )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    monkeypatch.setattr(oai, "OpenAI", lambda **kw: fake_client)

    provider = OpenAIProvider(api_key="sk-test")  # no on_token -> non-streaming
    turn = provider.send([])
    assert turn.text == "done"
    assert turn.tool_calls == []


def test_streamed_function_calls_replay_valid_protocol(monkeypatch):
    tools = ToolRegistry([ReadTool()]).schemas()
    requests = []

    def create(**kwargs):
        requests.append(kwargs)
        assert kwargs["stream"] is True
        assert kwargs["tools"] == tools
        if len(requests) == 1:
            return [
                _chunk(tool_calls=[
                    _tc(0, id="s1", name="read_", args='{"path":'),
                    _tc(1, id="s2", name="read_", args='{"path":'),
                ]),
                _chunk(tool_calls=[
                    _tc(1, name="file", args='"b.txt"}'),
                    _tc(0, name="file", args='"a.txt"}'),
                ]),
            ]
        assert kwargs["messages"][-3:] == [
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "s1", "type": "function", "function": {
                    "name": "read_file", "arguments": '{"path":"a.txt"}'}},
                {"id": "s2", "type": "function", "function": {
                    "name": "read_file", "arguments": '{"path":"b.txt"}'}},
            ]},
            {"role": "tool", "tool_call_id": "s1", "content": "alpha"},
            {"role": "tool", "tool_call_id": "s2", "content": "beta"},
        ]
        return [_chunk(content="done")]

    fake_client = SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(oai, "OpenAI", lambda **kw: fake_client)
    provider = OpenAIProvider(api_key="sk-test", system="system", on_token=lambda _: None)
    provider.add_user("read two files")
    turn = provider.send(tools)
    assert [(call.id, call.name, call.arguments) for call in turn.tool_calls] == [
        ("s1", "read_file", {"path": "a.txt"}),
        ("s2", "read_file", {"path": "b.txt"}),
    ]
    provider.add_tool_result("s1", "alpha")
    provider.add_tool_result("s2", "beta")
    assert provider.send(tools).text == "done"
    assert len(requests) == 2
