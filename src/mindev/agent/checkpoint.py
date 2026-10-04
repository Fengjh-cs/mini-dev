"""Git-based checkpoint for rolling back the agent's changes."""

import subprocess


class GitCheckpoint:
    def __init__(
        self, cwd: str | None = None, message: str = "mindev checkpoint"
    ) -> None:
        self._cwd = cwd
        self._message = message

    def _git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args], cwd=self._cwd, capture_output=True, text=True
        )

    def is_repo(self) -> bool:
        return self._git("rev-parse", "--is-inside-work-tree").returncode == 0

    def commit(self) -> str | None:
        """Commit pending changes; return the new HEAD hash, or None if no-op."""
        if not self.is_repo():
            return None
        if not self._git("status", "--porcelain").stdout.strip():
            return None
        self._git("add", "-A")
        if self._git("commit", "-m", self._message).returncode != 0:
            return None
        return self._git("rev-parse", "HEAD").stdout.strip() or None
