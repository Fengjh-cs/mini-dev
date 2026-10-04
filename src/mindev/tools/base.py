"""Tool abstraction."""

from abc import ABC, abstractmethod


class Tool(ABC):
    name: str = ""
    description: str = ""
    risk: str = "read"  # "read" | "write" | "command"

    @abstractmethod
    def parameters(self) -> dict:
        """Return the JSON Schema for the tool's arguments."""

    @abstractmethod
    def run(self, arguments: dict) -> str:
        """Execute the tool and return a string result for the model."""

    def schema(self) -> dict:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters(),
        }
