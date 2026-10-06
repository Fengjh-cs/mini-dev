"""Run commands in Docker with only the isolated workspace bind-mounted."""

import subprocess
from pathlib import Path

from .base import Sandbox

MAX_OUTPUT_CHARS = 20_000


class DockerSandbox(Sandbox):
    @property
    def shell_hint(self) -> str:
        return "POSIX sh syntax in Docker. The project copy is at /workspace; network is disabled."

    def __init__(
        self,
        host_dir: str,
        image: str = "python:3.13-slim",
        workspace: str = "/workspace",
    ) -> None:
        self._image = image
        self._workspace = workspace
        self._host_dir = str(Path(host_dir).resolve(strict=True))

    def build_command(self, command: str) -> list[str]:
        return [
            "docker", "run", "--rm", "--pull", "never",
            "--network", "none",
            "--read-only",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--pids-limit", "128",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=128m",
            "--mount", f"type=bind,source={self._host_dir},target={self._workspace}",
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
        if proc.returncode:
            return f"Error: command exited with status {proc.returncode}.\n{output}".rstrip()
        return output or "(no output)"
