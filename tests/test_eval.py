import os

from mindev.eval import Task, default_tasks, run_eval
from mindev.llm.base import LLMProvider, ToolCall, Turn


class ScriptedProvider(LLMProvider):
    def __init__(self, turns):
        self._turns = turns
        self._i = 0

    def add_user(self, content):
        pass

    def send(self, tools):
        turn = self._turns[self._i]
        self._i += 1
        return turn

    def add_tool_result(self, call_id, output):
        pass


def _factory_with(scripts):
    counter = [0]

    def factory():
        turns = scripts[counter[0]]
        counter[0] += 1
        return ScriptedProvider(turns)

    return factory


def test_eval_all_pass_with_scripted_provider(tmp_path):
    scripts = [
        [
            Turn("", [ToolCall("c1", "write_file", {"path": "hello.txt", "content": "hi"})]),
            Turn("done", []),
        ],
        [
            Turn("", [ToolCall("c1", "edit_file", {"path": "cfg.txt", "old_string": "name = old", "new_string": "name = new"})]),
            Turn("done", []),
        ],
        [
            Turn("", [ToolCall("c1", "bash", {"command": "echo x > out.txt"})]),
            Turn("done", []),
        ],
    ]
    results = run_eval(_factory_with(scripts), default_tasks(), str(tmp_path))
    assert [r.name for r in results] == ["write_file", "edit_file", "bash"]
    assert all(r.passed for r in results)


def test_eval_reports_failure(tmp_path):
    class Noop(LLMProvider):
        def add_user(self, content):
            pass

        def send(self, tools):
            return Turn("I won't do anything", [])

        def add_tool_result(self, call_id, output):
            pass

    task = Task(
        name="make_file",
        prompt="create f.txt",
        check=lambda d: os.path.exists(os.path.join(d, "f.txt")),
    )
    results = run_eval(lambda: Noop(), [task], str(tmp_path))
    assert results[0].passed is False
    assert results[0].output == "I won't do anything"
