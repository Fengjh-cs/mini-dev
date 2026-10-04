"""A tiny evaluation harness for mini-dev.

Runs the agent on a set of tasks in isolated directories and checks the
resulting filesystem to decide pass/fail. Works with any provider — a real LLM
or a scripted/mock one for deterministic testing.
"""

import os
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


@dataclass
class EvalResult:
    name: str
    passed: bool
    output: str


def _default_tools() -> ToolRegistry:
    return ToolRegistry([ReadTool(), WriteFileTool(), EditFileTool(), BashTool()])


def run_eval(provider_factory, tasks, root, tools=None) -> list[EvalResult]:
    """Run each task in its own subdirectory, then check the result."""
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

        results.append(EvalResult(task.name, task.check(workdir), output))
    return results


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
