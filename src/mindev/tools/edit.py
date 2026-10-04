"""Structured file-editing tools.

``write_file`` creates or overwrites a file; ``edit_file`` replaces a unique
occurrence of ``old_string`` with ``new_string`` (the same precise-edit
semantics Claude Code's Edit tool uses). Both snapshot the file first so the
change can be rolled back.
"""

from .base import Tool
from .snapshot import SnapshotStore

MAX_EDIT_CHARS = 100_000


class WriteFileTool(Tool):
    name = "write_file"
    description = "Create a new file, or overwrite an existing file, with the given content."

    def __init__(self, snapshots: SnapshotStore | None = None) -> None:
        self._snapshots = snapshots

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        }

    def run(self, arguments: dict) -> str:
        path = arguments.get("path", "")
        content = arguments.get("content", "")
        if not path:
            return "Error: path is required."
        if self._snapshots:
            self._snapshots.snapshot(path)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as exc:
            return f"Error: could not write {path}: {exc}"
        return f"Wrote {len(content)} chars to {path}."


class EditFileTool(Tool):
    name = "edit_file"
    description = (
        "Replace the unique occurrence of old_string in a file with new_string. "
        "old_string must appear exactly once, otherwise the edit is rejected."
    )

    def __init__(self, snapshots: SnapshotStore | None = None) -> None:
        self._snapshots = snapshots

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
            },
            "required": ["path", "old_string", "new_string"],
        }

    def run(self, arguments: dict) -> str:
        path = arguments.get("path", "")
        old = arguments.get("old_string", "")
        new = arguments.get("new_string", "")
        if not old:
            return "Error: old_string must not be empty."
        try:
            with open(path, encoding="utf-8") as f:
                original = f.read()
        except FileNotFoundError:
            return f"Error: file not found: {path}"
        except OSError as exc:
            return f"Error: could not read {path}: {exc}"

        if len(original) > MAX_EDIT_CHARS:
            return f"Error: file too large to edit ({len(original)} chars)."
        count = original.count(old)
        if count == 0:
            return f"Error: old_string not found in {path}."
        if count > 1:
            return f"Error: old_string is not unique (found {count} occurrences)."

        if self._snapshots:
            self._snapshots.snapshot(path)
        updated = original.replace(old, new, 1)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(updated)
        except OSError as exc:
            return f"Error: could not write {path}: {exc}"
        return f"Edited {path}: replaced 1 occurrence."
