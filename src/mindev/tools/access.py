"""Workspace path checks shared by model-facing file tools."""

import os
from pathlib import Path
from typing import Iterable


class AccessDenied(ValueError):
    """A tool path is outside the file access boundary."""


def _is_env_secret(part: str) -> bool:
    # Windows accepts trailing spaces/dots and NTFS stream suffixes as aliases
    # for the same base filename; reject those spellings before opening it.
    name = part.split(":", 1)[0].rstrip(" .").casefold()
    return name == ".env" or (name.startswith(".env.") and name != ".env.example")


class WorkspacePathPolicy:
    """Allow workspace reads; optionally restrict writes to named files.

    This checks paths at tool invocation time. It does not contain commands or
    protect against another process replacing a path during the file operation.
    """

    def __init__(self, root: str | os.PathLike[str],
                 allowed_writes: Iterable[str] | None = None) -> None:
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("workspace root must be a directory")
        self._allowed_writes: frozenset[str] | None = None
        if allowed_writes is not None:
            normalized: set[str] = set()
            for raw in allowed_writes:
                if not isinstance(raw, str) or not raw.strip() or Path(raw).is_absolute():
                    raise ValueError("allowed write paths must be relative files")
                try:
                    path = self.resolve(raw)
                except AccessDenied as exc:
                    raise ValueError(f"invalid allowed write path: {exc}") from exc
                if path == self.root or path.is_dir():
                    raise ValueError(f"allowed write path is not a file: {raw}")
                normalized.add(self._relative_key(path))
            if not normalized:
                raise ValueError("at least one allowed write file is required")
            self._allowed_writes = frozenset(normalized)

    def _relative_key(self, path: Path) -> str:
        relative = path.relative_to(self.root).as_posix()
        return relative.casefold() if os.name == "nt" else relative

    def resolve(self, path: str) -> Path:
        if not isinstance(path, str) or not path.strip():
            raise AccessDenied("access denied: path is required")
        submitted = Path(path)
        if any(_is_env_secret(part) for part in submitted.parts):
            raise AccessDenied("access denied: environment files are blocked")

        candidate = submitted if submitted.is_absolute() else self.root / submitted
        lexical = Path(os.path.abspath(candidate))
        if not lexical.is_relative_to(self.root):
            raise AccessDenied("access denied: path is outside workspace")

        current = self.root
        for part in lexical.relative_to(self.root).parts:
            current /= part
            if current.is_symlink():
                raise AccessDenied("access denied: symbolic links are blocked")

        try:
            resolved = lexical.resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            raise AccessDenied("access denied: path cannot be resolved") from exc
        if not resolved.is_relative_to(self.root):
            raise AccessDenied("access denied: path is outside workspace")
        if any(_is_env_secret(part) for part in resolved.relative_to(self.root).parts):
            raise AccessDenied("access denied: environment files are blocked")
        return resolved

    def resolve_write(self, path: str) -> Path:
        """Resolve a write target before any file is opened or snapshotted."""
        resolved = self.resolve(path)
        if (self._allowed_writes is not None
                and self._relative_key(resolved) not in self._allowed_writes):
            allowed = ", ".join(sorted(self._allowed_writes))
            raise AccessDenied(f"access denied: file is outside allowed write set; allowed: {allowed}")
        return resolved
