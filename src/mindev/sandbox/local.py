"""Run commands directly on the host (trusted local use only)."""

import os
import subprocess

from .base import Sandbox

MAX_OUTPUT_CHARS = 20_000


class LocalSandbox(Sandbox):
    def __init__(self, cwd: str | None = None) -> None:
        self._cwd = cwd or os.getcwd()

    @property
    def shell_hint(self) -> str:
        if os.name == "nt":
            return ("Windows PowerShell 5.1 syntax. Use Get-ChildItem, Get-Content, "
                    "and ';' between commands; avoid Bash-only syntax such as && and export.")
        return "POSIX sh syntax. Use ls, cat, pwd, and standard sh commands."

    @staticmethod
    def build_command(command: str, platform: str | None = None) -> list[str]:
        platform = platform or os.name
        if platform == "nt":
            return ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
                    "-Command", command]
        return ["/bin/sh", "-c", command]

    def run(self, command: str, timeout: int = 60) -> str:
        if not command.strip():
            return "Error: empty command."
        try:
            proc = subprocess.run(
                self.build_command(command),
                cwd=self._cwd,
                capture_output=True,
                text=True,
                errors="replace",
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
