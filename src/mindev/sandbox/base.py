"""Sandbox abstraction for running commands."""

from abc import ABC, abstractmethod


class Sandbox(ABC):
    @abstractmethod
    def run(self, command: str, timeout: int = 60) -> str:
        """Run a command and return combined stdout/stderr."""
