from jarvis.core.tool_request import ToolRequest
from jarvis.models.base import (
    ModelProvider,
    ModelRequest,
    ModelToolDefinition,
)
from jarvis.tools.service import ToolService


class AgentService:
    """
    Coordinates the AI model with JARVIS tools.

    The model is allowed to REQUEST a tool.

    The model never executes a tool directly.

    Every requested tool still goes through:

        ToolRequest
            -> ToolService
            -> PermissionPolicy
            -> ToolExecutor
            -> Tool

    This keeps the AI reasoning layer separate from
    the trusted JARVIS execution/security layer.
    """

    def __init__(
        self,
        model_provider: ModelProvider,
        tool_service: ToolService,
    ) -> None:
        self.model_provider = model_provider
        self.tool_service = tool_service

    def run(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        """
        Process one natural-language JARVIS request.

        For now there are two possible outcomes:

        1. The model answers normally.
        2. The model requests one or more tools.
           JARVIS securely executes them and returns
           their REAL results.

        A later milestone will send those real tool
        results back to the model for a polished
        natural-language final answer.
        """

        # Convert JARVIS's registered tools into the
        # generic format that any model provider can use.
        available_tools = [
            ModelToolDefinition(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters_schema,
            )
            for tool in self.tool_service.registry.tools()
        ]

        # Ask the model what it wants to do.
        model_response = self.model_provider.generate(
            ModelRequest(
                prompt=prompt,
                system_prompt=system_prompt,
                tools=available_tools,
            )
        )

        # If the model did not request a tool,
        # simply return its normal conversational answer.
        if not model_response.tool_calls:
            return model_response.text

        tool_results: list[str] = []

        # The model may request one or more tools.
        for tool_call in model_response.tool_calls:
            # Convert the AI's request into JARVIS's own
            # trusted ToolRequest type.
            request = ToolRequest(
                tool_name=tool_call.name,
                arguments=tool_call.arguments,
            )

            # IMPORTANT:
            #
            # We do NOT execute the tool directly.
            #
            # ToolService sends it through the existing
            # registry, permissions and executor system.
            result = self.tool_service.execute(
                request
            )

            tool_results.append(
                self._format_tool_result(
                    tool_call.name,
                    result,
                )
            )

        return "\n\n".join(tool_results)

    @staticmethod
    def _format_tool_result(
        tool_name: str,
        result: object,
    ) -> str:
        """
        Convert real tool results into readable text.

        This is intentionally deterministic.

        We do not ask the AI to invent or reinterpret
        the result at this stage.
        """

        if isinstance(result, list):
            if not result:
                formatted_result = "(empty)"
            else:
                formatted_result = "\n".join(
                    f"- {item}"
                    for item in result
                )

        elif isinstance(result, dict):
            if not result:
                formatted_result = "(empty)"
            else:
                formatted_result = "\n".join(
                    f"{key}: {value}"
                    for key, value in result.items()
                )

        else:
            formatted_result = str(result)

        return (
            f"Tool result from {tool_name}:\n"
            f"{formatted_result}"
        )