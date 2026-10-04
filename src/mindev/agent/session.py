"""Persist agent sessions to disk so they can be resumed."""

import json
import os

from ..llm.base import LLMProvider


class SessionStore:
    def __init__(self, path: str) -> None:
        self._path = path

    def exists(self) -> bool:
        return os.path.exists(self._path)

    def save(self, provider: LLMProvider) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(provider.export_state(), f, ensure_ascii=False, indent=2)

    def load(self, provider: LLMProvider) -> None:
        if not os.path.exists(self._path):
            return
        with open(self._path, encoding="utf-8") as f:
            provider.restore_state(json.load(f))
