from jarvis.core.agent_service import AgentService
from jarvis.core.conversation import Conversation
from jarvis.core.tool_request import ToolRequest
from jarvis.models.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
)
from jarvis.tools.service import ToolService


class JarvisApplication:
    """
    Main application facade for JARVIS.

    Interfaces such as:

    - CLI
    - future desktop UI
    - future mobile/dashboard interfaces

    should communicate with this class instead of
    directly controlling tools or model providers.
    """

    def __init__(
        self,
        tool_service: ToolService,
        model_provider: ModelProvider,
    ) -> None:
        self.tool_service = tool_service
        self.model_provider = model_provider

        self.agent_service = AgentService(
            model_provider=model_provider,
            tool_service=tool_service,
        )

        # Current active chat session.
        #
        # Later we will support several conversations
        # identified by IDs and persisted in PostgreSQL.
        self.conversation = Conversation()

    def execute_tool(
        self,
        request: ToolRequest,
    ) -> object:
        """
        Execute a direct tool request through JARVIS's
        trusted security pipeline.
        """

        return self.tool_service.execute(
            request
        )

    def ask(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> ModelResponse:
        """
        Perform a simple stateless model request.

        This remains available for internal operations
        that do not require agent tools or chat history.
        """

        request = ModelRequest(
            prompt=prompt,
            system_prompt=system_prompt,
        )

        return self.model_provider.generate(
            request
        )

    def ask_with_tools(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        """
        Main conversational JARVIS path.

        This uses:
        - conversation history
        - AI reasoning
        - tool calling
        - permissions
        - multi-step execution
        """

        return self.agent_service.run(
            prompt=prompt,
            system_prompt=system_prompt,
            conversation=self.conversation,
        )

    def new_conversation(self) -> None:
        """
        Clear the current in-memory chat and start fresh.
        """

        self.conversation.clear()

    def conversation_message_count(self) -> int:
        """
        Number of messages in the current chat.

        Mostly useful for debugging and status displays.
        """

        return len(
            self.conversation
        )