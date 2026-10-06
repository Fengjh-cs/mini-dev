"""Run a shell command via a sandbox."""

from ..sandbox.base import Sandbox
from ..sandbox.local import LocalSandbox
from .base import Tool


class BashTool(Tool):
    name = "bash"
    description = (
        "Run a shell command and return its combined stdout/stderr. "
        "Use for listing files, running tests, git, or build commands."
    )
    risk = "command"

    def __init__(self, sandbox: Sandbox | None = None) -> None:
        self._sandbox = sandbox or LocalSandbox()
        self.description = (
            "Run a shell command and return its combined stdout/stderr. "
            "Use for listing files, running tests, git, or build commands. "
            + self._sandbox.shell_hint
        )

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The command to run."},
            },
            "required": ["command"],
        }

    def run(self, arguments: dict) -> str:
        return self._sandbox.run(arguments.get("command", ""))
