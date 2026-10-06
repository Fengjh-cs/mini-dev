"""Run user-selected checks after a batch of successful file edits."""

from dataclasses import dataclass
from typing import Protocol

from ..sandbox.docker import CommandResult

MAX_RESULT_CHARS = 3_000


class CommandSandbox(Protocol):
    def run_result(self, command: str, timeout: int = 60) -> CommandResult: ...


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    output: str


class EditVerifier:
    def __init__(self, commands: list[str], sandbox: CommandSandbox,
                 timeout: int = 120) -> None:
        if not commands or any(not command.strip() for command in commands):
            raise ValueError("verification commands must not be empty")
        self.commands = tuple(commands)
        self._sandbox = sandbox
        self._timeout = timeout

    def run(self) -> VerificationResult:
        passed = True
        lines: list[str] = []
        for command in self.commands:
            result = self._sandbox.run_result(command, timeout=self._timeout)
            ok = result.exit_code == 0
            passed &= ok
            status = "PASS" if ok else "FAIL"
            code = "unavailable" if result.exit_code is None else str(result.exit_code)
            lines.append(f"[verify {status}] {command} (exit={code})")
            if result.output != "(no output)":
                output = result.output[:MAX_RESULT_CHARS]
                if len(result.output) > MAX_RESULT_CHARS:
                    output += "\n... (verification output truncated)"
                lines.append(output)
        if not passed:
            lines.append("Verification failed. Fix the edit and retry; checks run after the next edit.")
        return VerificationResult(passed, "\n".join(lines))
