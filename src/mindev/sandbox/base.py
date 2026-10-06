"""Sandbox abstraction for running commands."""

from abc import ABC, abstractmethod


class Sandbox(ABC):
    @property
    def shell_hint(self) -> str:
        """Describe the command syntax accepted by this sandbox."""
        return "Use the configured system shell."

    @abstractmethod
    def run(self, command: str, timeout: int = 60) -> str:
        """Run a command and return combined stdout/stderr."""
