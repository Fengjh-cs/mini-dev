"""Read a file and return its contents with line numbers."""

import os

from .access import AccessDenied, WorkspacePathPolicy
from .base import Tool

MAX_OUTPUT_CHARS = 20_000


class ReadTool(Tool):
    name = "read_file"
    description = (
        "Read a text file inside the workspace and return numbered lines. "
        "Environment files and symbolic links are blocked."
    )

    def __init__(self, access: WorkspacePathPolicy | None = None) -> None:
        self._access = access or WorkspacePathPolicy(os.getcwd())

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to read."},
            },
            "required": ["path"],
        }

    def run(self, arguments: dict) -> str:
        path = arguments.get("path", "")
        try:
            safe_path = self._access.resolve(path)
            with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except AccessDenied as exc:
            return f"Error: {exc}"
        except FileNotFoundError:
            return f"Error: file not found: {path}"
        except IsADirectoryError:
            return f"Error: {path} is a directory, not a file."
        except OSError as exc:
            return f"Error: could not read {path}: {exc}"

        numbered = "".join(f"{i + 1:4d} {line}" for i, line in enumerate(lines))
        if not numbered:
            return "(empty file)"
        if len(numbered) > MAX_OUTPUT_CHARS:
            numbered = numbered[:MAX_OUTPUT_CHARS] + "\n... (truncated)"
        return numbered
