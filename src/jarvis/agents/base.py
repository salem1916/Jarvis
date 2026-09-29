from abc import ABC, abstractmethod

from jarvis.core.action_confirmation import (
    ActionConfirmationHandler,
)
from jarvis.core.conversation import Conversation


class AgentEngine(ABC):
    """
    Provider-independent agent orchestration interface.

    Agent engines decide how a request is orchestrated.

    Examples:

        NativeAgentEngine
        HermesAgentEngine

    This is deliberately separate from ModelProvider.

    Agent engine:
        controls planning/orchestration.

    Model provider:
        communicates with the selected AI model.

    Trusted actions still pass through the JARVIS security
    and tool-execution layers.
    """

    name: str

    @abstractmethod
    def run(
        self,
        prompt: str,
        system_prompt: str | None = None,
        conversation: Conversation | None = None,
        confirmation_handler: (
            ActionConfirmationHandler
            | None
        ) = None,
    ) -> str:
        """
        Execute one agent request and return its final response.
        """

        raise NotImplementedError