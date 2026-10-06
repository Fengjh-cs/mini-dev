"""Check file scope and run selected commands after a batch of edits."""

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..sandbox.docker import CommandResult
from ..sandbox.workspace import SKIP_NAMES
from ..tools.access import WorkspacePathPolicy

MAX_RESULT_CHARS = 3_000


class CommandSandbox(Protocol):
    def run_result(self, command: str, timeout: int = 60) -> CommandResult: ...


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    output: str


class FileScopeCheck:
    """Compare the isolated copy with its pre-task contents, without Git metadata."""

    def __init__(self, workspace: Path, allowed_files: list[str],
                 ignored_files: tuple[str, ...] = ()) -> None:
        self.root = Path(workspace).resolve(strict=True)
        policy = WorkspacePathPolicy(self.root)
        self.allowed: set[str] = set()
        for raw in allowed_files:
            if Path(raw).is_absolute():
                raise ValueError("allowed file paths must be relative to the workspace")
            path = policy.resolve(raw)
            if path == self.root or path.is_dir():
                raise ValueError(f"allowed file is not a file path: {raw}")
            self.allowed.add(self._key(path.relative_to(self.root).as_posix()))
        if not self.allowed:
            raise ValueError("at least one allowed file is required")
        self.ignored = {
            self._key(Path(raw).resolve(strict=False).relative_to(self.root).as_posix())
            for raw in ignored_files
            if Path(raw).resolve(strict=False).is_relative_to(self.root)
        }
        self._initial = self._snapshot()

    @staticmethod
    def _key(path: str) -> str:
        return path.casefold() if os.name == "nt" else path

    def _snapshot(self) -> dict[str, bytes]:
        files: dict[str, bytes] = {}

        def visit(directory: Path) -> None:
            with os.scandir(directory) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    relative = path.relative_to(self.root).as_posix()
                    key = self._key(relative)
                    if key in self.ignored:
                        continue
                    info = entry.stat(follow_symlinks=False)
                    if (entry.is_symlink() or
                            getattr(info, "st_file_attributes", 0)
                            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
                        files[key] = b"<filesystem link>"
                    elif entry.is_dir(follow_symlinks=False):
                        if entry.name.casefold() not in SKIP_NAMES:
                            visit(path)
                    elif entry.is_file(follow_symlinks=False):
                        files[key] = hashlib.sha256(path.read_bytes()).digest()
                    else:
                        files[key] = b"<special file>"

        visit(self.root)
        return files

    def unexpected_changes(self) -> list[str]:
        current = self._snapshot()
        return sorted(
            path for path in self._initial.keys() | current.keys()
            if path not in self.allowed and self._initial.get(path) != current.get(path)
        )


class EditVerifier:
    def __init__(self, commands: list[str], sandbox: CommandSandbox | None = None,
                 timeout: int = 120, scope: FileScopeCheck | None = None) -> None:
        if (not commands and scope is None) or any(not command.strip() for command in commands):
            raise ValueError("verification commands must not be empty")
        if commands and sandbox is None:
            raise ValueError("verification commands require a sandbox")
        self.commands = tuple(commands)
        self._sandbox = sandbox
        self._timeout = timeout
        self._scope = scope

    def run(self) -> VerificationResult:
        passed = True
        lines: list[str] = []
        if self._scope is not None:
            unexpected = self._scope.unexpected_changes()
            if unexpected:
                lines.append("[verify FAIL] file scope: unexpected changes: "
                             + ", ".join(unexpected))
                lines.append("Allowed files: " + ", ".join(sorted(self._scope.allowed)))
                lines.append("Undo edits outside the allowed files. Use edit_file to revert "
                             "changes or delete_file to remove new files, then retry.")
                return VerificationResult(False, "\n".join(lines))
        for command in self.commands:
            assert self._sandbox is not None
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
        if self._scope is not None:
            unexpected = self._scope.unexpected_changes()
            if unexpected:
                passed = False
                lines.append("[verify FAIL] file scope: unexpected changes: "
                             + ", ".join(unexpected))
                lines.append("Allowed files: " + ", ".join(sorted(self._scope.allowed)))
                lines.append("Undo edits outside the allowed files. Use edit_file to revert "
                             "changes or delete_file to remove new files, then retry.")
            else:
                lines.insert(0, "[verify PASS] file scope")
        if not passed:
            lines.append("Verification failed. Fix the edit and retry; checks run after the next edit.")
        return VerificationResult(passed, "\n".join(lines))
