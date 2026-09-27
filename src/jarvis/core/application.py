from jarvis.core.agent_service import AgentService
from jarvis.core.conversation import Conversation
from jarvis.core.tool_request import ToolRequest
from jarvis.models.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
)
from jarvis.security.capabilities import Capability
from jarvis.security.policy import (
    PermissionDecision,
)
from jarvis.tools.service import ToolService


class JarvisApplication:
    """
    Main application facade for JARVIS.

    Interfaces such as:

    - CLI
    - desktop UI
    - future mobile/dashboard interfaces

    communicate with this class instead of directly
    controlling models, tools, or security internals.
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

        # Current active conversation.
        #
        # This is in-memory for now.
        #
        # Later conversations will receive IDs and
        # become persistent in PostgreSQL.
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

        This is useful for internal operations that
        do not require tools or conversation history.
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
        Clear the current in-memory conversation.
        """

        self.conversation.clear()

    def conversation_message_count(self) -> int:
        """
        Return the number of internal messages in
        the current conversation.

        Tool messages are included.
        """

        return len(
            self.conversation
        )

    def permission_decision(
        self,
        capability: Capability,
    ) -> PermissionDecision:
        """
        Query JARVIS's real security policy.

        The desktop UI uses this method to display
        permission state without reaching directly
        into ToolExecutor internals.

        This keeps the UI dependent on the application
        facade rather than security implementation details.
        """

        return self.tool_service.executor.policy.evaluate(
            capability
        )