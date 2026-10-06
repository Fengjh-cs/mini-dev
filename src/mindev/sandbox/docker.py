"""Run commands in Docker with only the isolated workspace bind-mounted."""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .base import Sandbox

MAX_OUTPUT_CHARS = 20_000


@dataclass(frozen=True)
class CommandResult:
    exit_code: int | None
    output: str


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

    def run_result(self, command: str, timeout: int = 60) -> CommandResult:
        if not command.strip():
            return CommandResult(None, "Error: empty command.")
        try:
            proc = subprocess.run(
                self.build_command(command),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError:
            return CommandResult(None, "Error: docker is not installed or not on PATH.")
        except subprocess.TimeoutExpired:
            return CommandResult(None, f"Error: command timed out after {timeout} seconds.")
        except OSError as exc:
            return CommandResult(None, f"Error: failed to start docker: {exc}")

        output = (proc.stdout or "") + (proc.stderr or "")
        if len(output) > MAX_OUTPUT_CHARS:
            output = output[:MAX_OUTPUT_CHARS] + "\n... (truncated)"
        return CommandResult(proc.returncode, output or "(no output)")

    def run(self, command: str, timeout: int = 60) -> str:
        result = self.run_result(command, timeout)
        if result.exit_code is None:
            return result.output
        if result.exit_code:
            return f"Error: command exited with status {result.exit_code}.\n{result.output}".rstrip()
        return result.output
