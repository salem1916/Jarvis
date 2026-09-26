from jarvis.core.agent_service import AgentService
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

    Interfaces such as the CLI and future desktop app
    communicate with this class instead of directly
    controlling models or tools.
    """

    def __init__(
        self,
        tool_service: ToolService,
        model_provider: ModelProvider,
    ) -> None:
        self.tool_service = tool_service
        self.model_provider = model_provider

        # AgentService connects AI reasoning to the
        # existing secured tool system.
        self.agent_service = AgentService(
            model_provider=model_provider,
            tool_service=tool_service,
        )

    def execute_tool(
        self,
        request: ToolRequest,
    ) -> object:
        """
        Execute a tool directly through JARVIS's
        trusted tool/security system.
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
        Perform a normal model request without
        automatic tool execution.

        We keep this because some future JARVIS tasks
        may only require the model.
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
        Run the secured AI + tool orchestration path.
        """

        return self.agent_service.run(
            prompt=prompt,
            system_prompt=system_prompt,
        )