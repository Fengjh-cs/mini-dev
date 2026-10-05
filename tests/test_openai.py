from types import SimpleNamespace

import mindev.llm.openai as oai
from mindev.llm.openai import OpenAIProvider


def _fake_client(response):
    last_kwargs = {}

    def create(**kwargs):
        last_kwargs.update(kwargs)
        return response

    chat = SimpleNamespace(completions=SimpleNamespace(create=create))
    return SimpleNamespace(chat=chat), last_kwargs


def _message(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def _response(message):
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_base_url_from_param(monkeypatch):
    captured = {}
    monkeypatch.setattr(oai, "OpenAI", lambda **kw: captured.update(kw))
    OpenAIProvider(api_key="sk-test", base_url="https://api.deepseek.com")
    assert captured["base_url"] == "https://api.deepseek.com"


def test_base_url_from_env(monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    captured = {}
    monkeypatch.setattr(oai, "OpenAI", lambda **kw: captured.update(kw))
    OpenAIProvider(api_key="sk-test")
    assert captured["base_url"] == "https://openrouter.ai/api/v1"


def test_send_parses_tool_call(monkeypatch):
    tc = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="read_file", arguments='{"path": "a.txt"}'),
    )
    client, _ = _fake_client(_response(_message(content=None, tool_calls=[tc])))
    monkeypatch.setattr(oai, "OpenAI", lambda **kw: client)

    provider = OpenAIProvider(api_key="sk-test")
    turn = provider.send([{"type": "function", "function": {"name": "read_file"}}])

    assert turn.text == ""
    assert len(turn.tool_calls) == 1
    assert turn.tool_calls[0].id == "call_1"
    assert turn.tool_calls[0].name == "read_file"
    assert turn.tool_calls[0].arguments == {"path": "a.txt"}
    assert provider._messages[-1]["role"] == "assistant"
    assert provider._messages[-1]["tool_calls"][0]["id"] == "call_1"


def test_send_returns_final_text(monkeypatch):
    client, last = _fake_client(_response(_message(content="all done", tool_calls=None)))
    monkeypatch.setattr(oai, "OpenAI", lambda **kw: client)

    provider = OpenAIProvider(api_key="sk-test")
    turn = provider.send([])

    assert turn.text == "all done"
    assert turn.tool_calls == []
    assert "tools" not in last  # empty tools are omitted


def test_add_tool_result_appends_tool_message():
    provider = OpenAIProvider(api_key="sk-test")
    provider.add_tool_result("call_1", "hello from tool")
    assert provider._messages[-1] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": "hello from tool",
    }
