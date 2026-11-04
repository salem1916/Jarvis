from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import ClassVar

from jarvis.security.capabilities import Capability


class Tool(ABC):
    internal_only: ClassVar[bool] = False
    name: ClassVar[str]
    description: ClassVar[str]
    required_capability: ClassVar[Capability]
    additional_capabilities: ClassVar[tuple[Capability,...]] = ()

    parameters_schema: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    @abstractmethod
    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> object:
        """Execute the tool."""
        raise NotImplementedError
