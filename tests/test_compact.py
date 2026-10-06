from types import SimpleNamespace

import mindev.llm.openai as oai
import pytest
from mindev.agent.loop import AgentLoop
from mindev.llm.base import LLMProvider, ToolCall, Turn
from mindev.llm.openai import OpenAIProvider
from mindev.tools.read import ReadTool
from mindev.tools.registry import ToolRegistry


class FakeProvider(LLMProvider):
    def __init__(self, turns, initial_tokens=0):
        self._turns = turns
        self._i = 0
        self._tokens = initial_tokens
        self.compact_calls = 0

    def add_user(self, content):
        self._tokens += 100

    def send(self, tools):
        turn = self._turns[self._i]
        self._i += 1
        self._tokens += 500
        return turn

    def add_tool_result(self, call_id, output):
        self._tokens += 200

    def context_tokens(self):
        return self._tokens

    def compact(self, keep_messages=6):
        self.compact_calls += 1
        self._tokens = 50
        return "summary"


def test_loop_compacts_when_over_threshold():
    turns = [
        Turn("", [ToolCall("c1", "read_file", {"path": "missing.txt"})]),
        Turn("done", []),
    ]
    provider = FakeProvider(turns, initial_tokens=1000)
    loop = AgentLoop(provider, ToolRegistry([ReadTool()]), compact_threshold=500)
    assert loop.run("task") == "done"
    assert provider.compact_calls >= 1


def test_loop_no_compact_when_under_threshold():
    provider = FakeProvider([Turn("done", [])], initial_tokens=50)
    loop = AgentLoop(provider, ToolRegistry([ReadTool()]), compact_threshold=500)
    loop.run("task")
    assert provider.compact_calls == 0


def test_openai_context_tokens():
    provider = OpenAIProvider(api_key="sk-test")
    provider._messages = [
        {"role": "system", "content": "abcd"},
        {"role": "user", "content": "hello world"},
    ]
    assert provider.context_tokens() == (4 + 11) // 4


def test_openai_compact_rebuilds_history(monkeypatch):
    def create(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="THE SUMMARY"))]
        )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    monkeypatch.setattr(oai, "OpenAI", lambda **kw: fake_client)

    provider = OpenAIProvider(api_key="sk-test")
    provider._messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "m1"},
        {"role": "assistant", "content": "m2"},
        {"role": "user", "content": "m3"},
        {"role": "assistant", "content": "m4"},
    ]
    summary = provider.compact(keep_messages=2)

    assert summary == "THE SUMMARY"
    assert len(provider._messages) == 4  # system + summary + last 2
    assert provider._messages[0] == {"role": "system", "content": "sys"}
    assert "THE SUMMARY" in provider._messages[1]["content"]
    assert provider._messages[2] == {"role": "user", "content": "m3"}
    assert provider._messages[3] == {"role": "assistant", "content": "m4"}


def test_openai_compact_noop_when_short():
    provider = OpenAIProvider(api_key="sk-test")
    provider._messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "m1"},
    ]
    assert provider.compact(keep_messages=6) == ""
    assert len(provider._messages) == 2


def test_openai_compact_keeps_tool_call_batch_together(monkeypatch):
    def create(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="TOOL SUMMARY"))]
        )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    monkeypatch.setattr(oai, "OpenAI", lambda **kw: fake_client)

    provider = OpenAIProvider(api_key="sk-test")
    provider._messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "read six files"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": str(i), "type": "function", "function": {"name": "read_file", "arguments": "{}"}}
                for i in range(6)
            ],
        },
        *[
            {"role": "tool", "tool_call_id": str(i), "content": f"result {i}"}
            for i in range(6)
        ],
    ]

    assert provider.compact(keep_messages=6) == "TOOL SUMMARY"
    assert provider._messages == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "[Earlier conversation summary]\nTOOL SUMMARY"},
    ]


def _assert_complete_tool_pairs(messages):
    """Match the Chat Completions rule: each call has one adjacent tool result."""
    pending = set()
    for message in messages:
        if message["role"] == "tool":
            assert message["tool_call_id"] in pending
            pending.remove(message["tool_call_id"])
        else:
            assert not pending, "assistant tool batch was split before all results"
            if message["role"] == "assistant" and message.get("tool_calls"):
                ids = [call["id"] for call in message["tool_calls"]]
                assert len(ids) == len(set(ids))
                pending = set(ids)
    assert not pending, "assistant tool batch is missing a result"


@pytest.mark.parametrize("keep_messages", [2, 3, 4, 5, 7, 8, 9])
def test_compact_never_splits_multi_tool_batches_at_cut_boundary(monkeypatch, keep_messages):
    """Every possible cut through either batch must leave a valid next request."""
    normal_requests = []
    request_count = 0

    def create(**kwargs):
        nonlocal request_count
        request_count += 1
        messages = kwargs["messages"]
        if request_count == 1:
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content="SUMMARY"))])
        _assert_complete_tool_pairs(messages)
        normal_requests.append(messages)
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content="done", tool_calls=None))])

    fake_client = SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(oai, "OpenAI", lambda **kw: fake_client)

    def assistant(*ids):
        return {"role": "assistant", "content": "", "tool_calls": [
            {"id": call_id, "type": "function", "function": {
                "name": "read_file", "arguments": "{}"}}
            for call_id in ids
        ]}

    def tool(call_id):
        return {"role": "tool", "tool_call_id": call_id, "content": call_id}

    provider = OpenAIProvider(api_key="sk-test", system="sys")
    provider._messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "first"},
        assistant("a", "b"), tool("a"), tool("b"),
        {"role": "user", "content": "second"},
        assistant("c", "d", "e"), tool("c"), tool("d"), tool("e"),
        {"role": "user", "content": "latest"},
    ]

    assert provider.compact(keep_messages=keep_messages) == "SUMMARY"
    _assert_complete_tool_pairs(provider._messages)
    assert provider.send([]).text == "done"
    assert len(normal_requests) == 1
    assert request_count == 2
