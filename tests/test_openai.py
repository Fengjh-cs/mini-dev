from types import SimpleNamespace

import mindev.llm.openai as oai
from mindev.llm.openai import OpenAIProvider
from mindev.tools.read import ReadTool
from mindev.tools.registry import ToolRegistry


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


def test_function_call_protocol_roundtrip_nonstream(monkeypatch):
    """The next request must replay the assistant call and both matching results."""
    tools = ToolRegistry([ReadTool()]).schemas()
    first = [
        SimpleNamespace(id="call_a", function=SimpleNamespace(
            name="read_file", arguments='{"path":"a.txt"}')),
        SimpleNamespace(id="call_b", function=SimpleNamespace(
            name="read_file", arguments='{"path":"b.txt"}')),
    ]
    expected_calls = [
        {"id": "call_a", "type": "function", "function": {
            "name": "read_file", "arguments": '{"path":"a.txt"}'}},
        {"id": "call_b", "type": "function", "function": {
            "name": "read_file", "arguments": '{"path":"b.txt"}'}},
    ]
    request_count = 0

    def create(**kwargs):
        nonlocal request_count
        request_count += 1
        assert kwargs["tools"] == tools
        assert len(kwargs["tools"]) == 1
        assert set(kwargs["tools"][0]) == {"type", "function"}
        assert kwargs["tools"][0]["type"] == "function"
        assert set(kwargs["tools"][0]["function"]) == {
            "name", "description", "parameters"}
        if request_count == 1:
            assert kwargs["messages"] == [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "read two files"},
            ]
            return _response(_message(tool_calls=first))
        assert kwargs["messages"][-3:] == [
            {"role": "assistant", "content": "", "tool_calls": expected_calls},
            {"role": "tool", "tool_call_id": "call_a", "content": "alpha"},
            {"role": "tool", "tool_call_id": "call_b", "content": "beta"},
        ]
        return _response(_message(content="done"))

    fake_client = SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(oai, "OpenAI", lambda **kw: fake_client)
    provider = OpenAIProvider(api_key="sk-test", system="system")
    provider.add_user("read two files")
    turn = provider.send(tools)
    assert [(call.id, call.name, call.arguments) for call in turn.tool_calls] == [
        ("call_a", "read_file", {"path": "a.txt"}),
        ("call_b", "read_file", {"path": "b.txt"}),
    ]
    provider.add_tool_result("call_a", "alpha")
    provider.add_tool_result("call_b", "beta")
    assert provider.send(tools).text == "done"
    assert request_count == 2
