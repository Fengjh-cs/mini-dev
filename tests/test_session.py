from mindev.agent.session import SessionStore
from mindev.llm.openai import OpenAIProvider


def test_openai_export_restore_roundtrip():
    provider = OpenAIProvider(api_key="sk-test")
    provider._messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
    ]
    state = provider.export_state()

    fresh = OpenAIProvider(api_key="sk-test")
    fresh.restore_state(state)
    assert fresh._messages == provider._messages


def test_session_store_save_load(tmp_path):
    path = str(tmp_path / "session.json")
    p1 = OpenAIProvider(api_key="sk-test")
    p1._messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "hi"},
    ]

    SessionStore(path).save(p1)

    p2 = OpenAIProvider(api_key="sk-test")
    SessionStore(path).load(p2)
    assert p2._messages == p1._messages


def test_session_store_load_missing_is_noop(tmp_path):
    store = SessionStore(str(tmp_path / "nope.json"))
    p = OpenAIProvider(api_key="sk-test")
    store.load(p)  # no error; keeps the default system message
    assert len(p._messages) == 1
