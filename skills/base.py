from abc import ABC, abstractmethod
from typing import Any, Dict


class AbstractSkill(ABC):
    """Base class for all agent skills (tools).

    Subclasses must define the four class-level attributes and implement
    the ``execute`` method.
    """

    name: str
    description: str
    input_schema: dict
    permission: str

    @abstractmethod
    def execute(self, arguments: Dict[str, Any], settings: Dict[str, Any]) -> dict:
        """Run the skill and return a result dict."""
        ...

    def to_tool_definition(self) -> dict:
        """Return a Claude-compatible tool definition dict."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "permission": self.permission,
        }
