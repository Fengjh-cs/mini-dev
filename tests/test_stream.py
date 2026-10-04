from types import SimpleNamespace

import mindev.llm.openai as oai
from mindev.llm.openai import OpenAIProvider


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
