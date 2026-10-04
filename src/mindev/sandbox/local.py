"""Run commands directly on the host (trusted local use only)."""

import subprocess

from .base import Sandbox

MAX_OUTPUT_CHARS = 20_000


class LocalSandbox(Sandbox):
    def run(self, command: str, timeout: int = 60) -> str:
        if not command.strip():
            return "Error: empty command."
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return f"Error: command timed out after {timeout} seconds."
        except OSError as exc:
            return f"Error: failed to run command: {exc}"

        output = (proc.stdout or "") + (proc.stderr or "")
        if len(output) > MAX_OUTPUT_CHARS:
            output = output[:MAX_OUTPUT_CHARS] + "\n... (truncated)"
        return output or "(no output)"
