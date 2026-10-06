"""Create a disposable, persistent copy for one agent run.

Only regular files and directories are copied. Git metadata, common build
artifacts, environment files, and filesystem links are deliberately omitted.
The returned directory is left on disk for review; nothing is synced back.
"""

import os
import shutil
import stat
import tempfile
from pathlib import Path

from ..tools.access import _is_env_secret


SKIP_NAMES = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".tox", ".idea", ".vscode",
    ".pytest-workspace-tmp", "dist", "build", "htmlcov",
}


def create_workspace(source: str | os.PathLike[str],
                     destination: str | os.PathLike[str] | None = None) -> Path:
    """Copy a source tree into a new, separate directory and return its path."""
    root = Path(source).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("source workspace must be a directory")

    if destination is None:
        target = Path(tempfile.mkdtemp(prefix="mindev-workspace-"))
    else:
        target = Path(destination).absolute()
        if target.exists():
            raise FileExistsError(f"isolated workspace already exists: {target}")
        proposed = target.parent.resolve(strict=False) / target.name
        if proposed.is_relative_to(root) or root.is_relative_to(proposed):
            raise ValueError("isolated workspace must be outside the source tree")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.mkdir()

    target = target.resolve(strict=True)
    if target.is_relative_to(root) or root.is_relative_to(target):
        target.rmdir()
        raise ValueError("isolated workspace must be outside the source tree")

    def copy_directory(src: Path, dst: Path) -> None:
        with os.scandir(src) as entries:
            for entry in entries:
                if entry.name.casefold() in SKIP_NAMES or _is_env_secret(entry.name):
                    continue
                candidate = Path(entry.path)
                # Junctions may not report as symlinks and can create cycles.
                attrs = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
                if (entry.is_symlink()
                        or attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
                        or not candidate.resolve(strict=True).is_relative_to(root)):
                    continue
                output = dst / entry.name
                if entry.is_dir(follow_symlinks=False):
                    output.mkdir()
                    copy_directory(candidate, output)
                elif entry.is_file(follow_symlinks=False):
                    shutil.copy2(candidate, output, follow_symlinks=False)

    copy_directory(root, target)
    return target
