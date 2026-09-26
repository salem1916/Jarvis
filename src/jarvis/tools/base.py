from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import ClassVar

from jarvis.security.capabilities import Capability


class Tool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    required_capability: ClassVar[Capability]

    @abstractmethod
    def execute(self, arguments: Mapping[str, object]) -> object:
        """Execute the tool."""
        raise NotImplementedError