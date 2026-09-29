from jarvis.agents.base import AgentEngine
from jarvis.core.action_confirmation import (
    ActionConfirmationHandler,
)
from jarvis.core.agent_service import AgentService
from jarvis.core.conversation import Conversation


class NativeAgentEngine(
    AgentEngine
):
    """
    Adapter exposing the existing JARVIS AgentService through
    the generic AgentEngine interface.

    This means the 144-test native agent remains usable even
    after Hermes is added.
    """

    name = "native"

    def __init__(
        self,
        agent_service: AgentService,
    ) -> None:
        self.agent_service = (
            agent_service
        )

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
        return self.agent_service.run(
            prompt=prompt,
            system_prompt=system_prompt,
            conversation=conversation,
            confirmation_handler=(
                confirmation_handler
            ),
        )