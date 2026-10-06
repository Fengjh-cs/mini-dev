"""Run commands inside a Docker container for process/network isolation.

Note: the workspace directory is bind-mounted read-write, so this isolates the
*process* and *network* but not the workspace filesystem. A full copy-in /
sync-back sandbox is a later refinement (Phase 5).
"""

import os
import subprocess

from .base import Sandbox

MAX_OUTPUT_CHARS = 20_000


class DockerSandbox(Sandbox):
    @property
    def shell_hint(self) -> str:
        return "POSIX sh syntax inside the Docker container."

    def __init__(
        self,
        image: str = "python:3.13-slim",
        workspace: str = "/workspace",
        host_dir: str | None = None,
    ) -> None:
        self._image = image
        self._workspace = workspace
        self._host_dir = host_dir or os.getcwd()

    def build_command(self, command: str) -> list[str]:
        return [
            "docker", "run", "--rm",
            "--network", "none",
            "-v", f"{self._host_dir}:{self._workspace}",
            "-w", self._workspace,
            self._image,
            "sh", "-c", command,
        ]

    def run(self, command: str, timeout: int = 60) -> str:
        if not command.strip():
            return "Error: empty command."
        try:
            proc = subprocess.run(
                self.build_command(command),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError:
            return "Error: docker is not installed or not on PATH."
        except subprocess.TimeoutExpired:
            return f"Error: command timed out after {timeout} seconds."

        output = (proc.stdout or "") + (proc.stderr or "")
        if len(output) > MAX_OUTPUT_CHARS:
            output = output[:MAX_OUTPUT_CHARS] + "\n... (truncated)"
        return output or "(no output)"
