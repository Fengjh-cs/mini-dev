"""A tiny evaluation harness for mini-dev.

Runs the agent on a set of tasks in isolated directories and checks the
resulting filesystem (hard check) plus, optionally, an LLM judge that scores
the output against a rubric (soft check).
"""

import os
import re
from collections.abc import Callable
from dataclasses import dataclass

from .agent.loop import AgentLoop
from .tools.bash import BashTool
from .tools.edit import EditFileTool, WriteFileTool
from .tools.read import ReadTool
from .tools.registry import ToolRegistry


@dataclass
class Task:
    name: str
    prompt: str
    check: Callable[[str], bool]
    setup: Callable[[str], None] = lambda d: None
    rubric: str | None = None  # optional rubric for an LLM judge


@dataclass
class EvalResult:
    name: str
    passed: bool
    output: str
    score: float | None = None  # soft score in [0, 1], when a judge is used


class LLMJudge:
    """Scores an agent's output against a rubric using a fresh LLM provider."""

    def __init__(self, provider_factory) -> None:
        self._factory = provider_factory

    def score(self, task: Task, output: str) -> float:
        provider = self._factory()
        rubric = task.rubric or "Correctness and completeness."
        provider.add_user(
            f"Task: {task.prompt}\n"
            f"Rubric: {rubric}\n\n"
            f"Agent output:\n{output}\n\n"
            "Score the output from 0 to 10. Reply with only the integer."
        )
        turn = provider.send([])
        match = re.search(r"\d+", turn.text)
        if not match:
            return 0.0
        return min(10, int(match.group())) / 10.0


def _default_tools() -> ToolRegistry:
    return ToolRegistry([ReadTool(), WriteFileTool(), EditFileTool(), BashTool()])


def run_eval(provider_factory, tasks, root, tools=None, judge=None) -> list[EvalResult]:
    """Run each task in its own subdirectory, then check + score the result."""
    results = []
    for task in tasks:
        workdir = os.path.join(root, task.name)
        os.makedirs(workdir, exist_ok=True)
        task.setup(workdir)

        original = os.getcwd()
        try:
            os.chdir(workdir)
            loop = AgentLoop(provider_factory(), tools or _default_tools())
            output = loop.run(task.prompt)
        finally:
            os.chdir(original)

        score = judge.score(task, output) if judge is not None else None
        results.append(EvalResult(task.name, task.check(workdir), output, score))
    return results


def summarize(results: list[EvalResult]) -> dict:
    passed = sum(1 for r in results if r.passed)
    scores = [r.score for r in results if r.score is not None]
    return {
        "total": len(results),
        "passed": passed,
        "pass_rate": passed / len(results) if results else 0.0,
        "avg_score": sum(scores) / len(scores) if scores else None,
    }


# --- example tasks ---------------------------------------------------------


def _check_hello(d: str) -> bool:
    p = os.path.join(d, "hello.txt")
    return os.path.exists(p) and open(p, encoding="utf-8").read().strip() == "hi"


def _setup_edit(d: str) -> None:
    with open(os.path.join(d, "cfg.txt"), "w", encoding="utf-8") as f:
        f.write("name = old\n")


def _check_edit(d: str) -> bool:
    with open(os.path.join(d, "cfg.txt"), encoding="utf-8") as f:
        return "name = new" in f.read()


def _check_mkfile(d: str) -> bool:
    return os.path.exists(os.path.join(d, "out.txt"))


def default_tasks() -> list[Task]:
    return [
        Task(
            name="write_file",
            prompt="Create a file named hello.txt containing exactly the text 'hi'.",
            check=_check_hello,
        ),
        Task(
            name="edit_file",
            prompt="In cfg.txt change 'name = old' to 'name = new'.",
            setup=_setup_edit,
            check=_check_edit,
        ),
        Task(
            name="bash",
            prompt="Run a shell command to create a file named out.txt.",
            check=_check_mkfile,
        ),
    ]
