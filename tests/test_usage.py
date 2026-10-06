from types import SimpleNamespace

import pytest

import mindev.llm.openai as oai
from mindev.llm.openai import OpenAIProvider
from mindev.llm.usage import ApiUsageTracker


def _usage(prompt, completion):
    return SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion,
                           total_tokens=prompt + completion)


def _response(text, usage=None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
        content=text, tool_calls=None))], usage=usage)


def test_nonstream_and_compaction_usage_includes_summary_call(monkeypatch):
    responses = [_response("done", _usage(10, 2)),
                 _response("summary", _usage(30, 4))]
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kw: responses.pop(0))))
    monkeypatch.setattr(oai, "OpenAI", lambda **kw: fake)
    tracker = ApiUsageTracker()
    provider = OpenAIProvider(api_key="sk-test", usage_tracker=tracker)
    provider.add_user("task")
    assert provider.send([]).text == "done"
    assert provider._summarize([{"role": "user", "content": "task"}]) == "summary"
    assert tracker.summary() == {
        "source": "api_response_usage", "requests": 2, "reported_requests": 2,
        "missing_usage_requests": 0, "complete": True,
        "prompt_tokens": 40, "completion_tokens": 6, "total_tokens": 46,
        "by_kind": {"agent": {"requests": 1, "reported_requests": 1},
                    "compaction": {"requests": 1, "reported_requests": 1}},
    }


def test_missing_usage_is_unknown_and_shared_explore_is_counted(monkeypatch):
    responses = [_response("main"), _response("explore", _usage(3, 1))]
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kw: responses.pop(0))))
    monkeypatch.setattr(oai, "OpenAI", lambda **kw: fake)
    tracker = ApiUsageTracker()
    OpenAIProvider(api_key="sk-test", usage_tracker=tracker).send([])
    OpenAIProvider(api_key="sk-test", usage_tracker=tracker,
                   usage_kind="explore").send([])
    report = tracker.summary()
    assert report["requests"] == 2
    assert report["reported_requests"] == 1
    assert report["missing_usage_requests"] == 1
    assert report["complete"] is False
    assert report["total_tokens"] is None
    assert report["by_kind"]["explore"]["reported_requests"] == 1


def test_stream_usage_only_final_chunk_is_recorded(monkeypatch):
    requested = {}

    def create(**kwargs):
        requested.update(kwargs)
        return [
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
                content="hello", tool_calls=None))], usage=None),
            SimpleNamespace(choices=[], usage=_usage(7, 2)),
        ]

    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(oai, "OpenAI", lambda **kw: fake)
    tracker = ApiUsageTracker()
    provider = OpenAIProvider(api_key="sk-test", on_token=lambda _: None,
                              usage_tracker=tracker)
    assert provider.send([]).text == "hello"
    assert requested["stream_options"] == {"include_usage": True}
    assert tracker.summary()["total_tokens"] == 9


def test_failed_api_request_makes_usage_incomplete(monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("synthetic API failure")

    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail)))
    monkeypatch.setattr(oai, "OpenAI", lambda **kw: fake)
    tracker = ApiUsageTracker()
    provider = OpenAIProvider(api_key="sk-test", usage_tracker=tracker)
    with pytest.raises(RuntimeError, match="synthetic API failure"):
        provider.send([])
    assert tracker.summary()["missing_usage_requests"] == 1
    assert tracker.summary()["total_tokens"] is None
