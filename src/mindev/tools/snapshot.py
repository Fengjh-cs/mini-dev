"""Snapshot original file state before edits so changes can be rolled back."""

import os
from dataclasses import dataclass


@dataclass
class _State:
    existed: bool
    content: str | None


class SnapshotStore:
    """Remembers the earliest pre-edit state of each file, and can restore it."""

    def __init__(self) -> None:
        self._states: dict[str, _State] = {}

    def snapshot(self, path: str) -> None:
        if path in self._states:
            return
        try:
            with open(path, encoding="utf-8") as f:
                self._states[path] = _State(True, f.read())
        except FileNotFoundError:
            self._states[path] = _State(False, None)

    def restore(self, path: str) -> None:
        state = self._states.pop(path, None)
        if state is None:
            return
        if state.existed:
            with open(path, "w", encoding="utf-8") as f:
                f.write(state.content or "")
        else:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
