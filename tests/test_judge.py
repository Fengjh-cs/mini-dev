from mindev.eval import LLMJudge, EvalResult, Task, default_tasks, run_eval, summarize
from mindev.llm.base import LLMProvider, ToolCall, Turn
from mindev.sandbox.local import LocalSandbox


class _Provider(LLMProvider):
    def __init__(self, text):
        self._text = text

    def add_user(self, content):
        pass

    def send(self, tools):
        return Turn(self._text, [])

    def add_tool_result(self, call_id, output):
        pass


def test_llm_judge_parses_score():
    judge = LLMJudge(lambda: _Provider("Score: 8"))
    task = Task(name="t", prompt="p", check=lambda d: True, rubric="r")
    assert judge.score(task, "output") == 0.8


def test_llm_judge_no_number_returns_zero():
    judge = LLMJudge(lambda: _Provider("no score here"))
    task = Task(name="t", prompt="p", check=lambda d: True)
    assert judge.score(task, "output") == 0.0


def test_summarize():
    results = [
        EvalResult("a", True, "out", 0.8),
        EvalResult("b", False, "out", 0.4),
    ]
    s = summarize(results)
    assert s["total"] == 2
    assert s["passed"] == 1
    assert s["pass_rate"] == 0.5
    assert abs(s["avg_score"] - 0.6) < 1e-9


def test_run_eval_attaches_judge_score(tmp_path):
    turns = [
        [Turn("", [ToolCall("c1", "write_file", {"path": "hello.txt", "content": "hi"})]), Turn("done", [])],
        [Turn("", [ToolCall("c1", "edit_file", {"path": "cfg.txt", "old_string": "name = old", "new_string": "name = new"})]), Turn("done", [])],
        [Turn("", [ToolCall("c1", "bash", {"command": "echo x > out.txt"})]), Turn("done", [])],
    ]
    counter = [0]

    class Scripted(LLMProvider):
        def __init__(self):
            self._turns = turns[counter[0]]
            counter[0] += 1
            self._i = 0

        def add_user(self, content):
            pass

        def send(self, tools):
            turn = self._turns[self._i]
            self._i += 1
            return turn

        def add_tool_result(self, call_id, output):
            pass

    judge = LLMJudge(lambda: _Provider("Score: 9"))
    results = run_eval(lambda: Scripted(), default_tasks(), str(tmp_path), judge=judge,
                       sandbox_factory=lambda d: LocalSandbox(cwd=d))
    assert all(r.passed for r in results)
    assert all(r.score == 0.9 for r in results)
