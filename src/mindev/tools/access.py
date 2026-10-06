"""Workspace path checks shared by model-facing file tools."""

import os
from pathlib import Path


class AccessDenied(ValueError):
    """A tool path is outside the file access boundary."""


def _is_env_secret(part: str) -> bool:
    # Windows accepts trailing spaces/dots and NTFS stream suffixes as aliases
    # for the same base filename; reject those spellings before opening it.
    name = part.split(":", 1)[0].rstrip(" .").casefold()
    return name == ".env" or (name.startswith(".env.") and name != ".env.example")


class WorkspacePathPolicy:
    """Allow ordinary files under one workspace; deny secret and symlink paths.

    This checks paths at tool invocation time. It does not contain commands or
    protect against another process replacing a path during the file operation.
    """

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("workspace root must be a directory")

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
