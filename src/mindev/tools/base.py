"""Tool abstraction."""

from abc import ABC, abstractmethod

import jsonschema


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

    def validate(self, arguments: dict) -> str | None:
        """Return an error message if arguments don't match the schema, else None."""
        if not isinstance(arguments, dict):
            return "arguments must be a JSON object"
        try:
            jsonschema.validate(instance=arguments, schema=self.parameters())
        except jsonschema.ValidationError as exc:
            return f"invalid arguments: {exc.message}"
        return None
