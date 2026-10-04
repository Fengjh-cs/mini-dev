"""Run a shell command and capture its output.

Phase 1 runs commands directly on the host (trusted local use only). A
sandbox is added in Phase 2.
"""

import subprocess

from .base import Tool

MAX_OUTPUT_CHARS = 20_000


class BashTool(Tool):
    name = "bash"
    description = (
        "Run a shell command and return its combined stdout/stderr. "
        "Use for listing files, running tests, git, or build commands."
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
        command = arguments.get("command", "")
        if not command.strip():
            return "Error: empty command."
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            return "Error: command timed out after 60 seconds."
        except OSError as exc:
            return f"Error: failed to run command: {exc}"

        output = (proc.stdout or "") + (proc.stderr or "")
        if len(output) > MAX_OUTPUT_CHARS:
            output = output[:MAX_OUTPUT_CHARS] + "\n... (truncated)"
        return output or "(no output)"
