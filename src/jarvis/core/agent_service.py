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

    The model is allowed to REQUEST tools.

    The model never executes tools directly.

    Every requested tool still goes through:

        ModelToolCall
            -> ToolRequest
            -> ToolService
            -> PermissionPolicy
            -> ToolExecutor
            -> Tool

    After JARVIS receives the REAL tool result,
    the result is sent back to the model so it can
    produce a natural-language final answer.
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

        Current flow:

        1. Give the model the available tools.
        2. Let the model decide whether a tool is needed.
        3. Execute requested tools through JARVIS security.
        4. Collect the REAL tool results.
        5. Send those verified results back to the model.
        6. Return a natural-language final answer.

        This is currently a single tool round.

        Multi-step agent loops will be added later.
        """

        # -------------------------------------------------
        # STEP 1:
        # Convert the real registered JARVIS tools into
        # model-independent tool definitions.
        # -------------------------------------------------

        available_tools = [
            ModelToolDefinition(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters_schema,
            )
            for tool in self.tool_service.registry.tools()
        ]

        # -------------------------------------------------
        # STEP 2:
        # Ask the model what it wants to do.
        #
        # The model can either:
        #
        # A. answer normally
        #
        # or
        #
        # B. return one or more ModelToolCall objects
        # -------------------------------------------------

        model_response = self.model_provider.generate(
            ModelRequest(
                prompt=prompt,
                system_prompt=system_prompt,
                tools=available_tools,
            )
        )

        # -------------------------------------------------
        # STEP 3:
        # If no tool is required, simply return the
        # model's normal conversational answer.
        # -------------------------------------------------

        if not model_response.tool_calls:
            return model_response.text

        # -------------------------------------------------
        # STEP 4:
        # Execute every requested tool through the REAL
        # JARVIS execution/security pipeline.
        #
        # The AI never calls tool.execute() itself.
        # -------------------------------------------------

        tool_results: list[str] = []

        for tool_call in model_response.tool_calls:
            # Convert the model's tool request into
            # JARVIS's trusted ToolRequest format.
            request = ToolRequest(
                tool_name=tool_call.name,
                arguments=tool_call.arguments,
            )

            # This passes through:
            #
            # ToolService
            #     -> ToolRegistry
            #     -> PermissionPolicy
            #     -> ToolExecutor
            #
            # so the AI cannot bypass permissions.
            result = self.tool_service.execute(
                request
            )

            # Convert the real Python result into
            # deterministic readable text.
            formatted_result = self._format_tool_result(
                tool_call.name,
                result,
            )

            tool_results.append(
                formatted_result
            )

        # -------------------------------------------------
        # STEP 5:
        # Combine all VERIFIED results.
        # -------------------------------------------------

        verified_results = "\n\n".join(
            tool_results
        )

        # -------------------------------------------------
        # STEP 6:
        # Ask the model to turn ONLY the verified tool
        # data into a natural-language answer.
        #
        # IMPORTANT:
        # We do NOT provide tools on this second call.
        #
        # This second request is only for formatting and
        # explaining data that JARVIS already obtained.
        # -------------------------------------------------

        final_prompt = (
            "The user originally asked:\n"
            f"{prompt}\n\n"
            "JARVIS executed the required tools and "
            "received these VERIFIED results:\n\n"
            f"{verified_results}\n\n"
            "Answer the user's original question using "
            "only the verified results above. "
            "Do not invent additional files, values, "
            "actions, or capabilities. "
            "Do not say that you performed an action "
            "unless it is represented in the verified "
            "tool results. "
            "Keep the answer concise and natural."
        )

        final_system_prompt = (
            "You are JARVIS, Salem's personal AI assistant. "
            "JARVIS has already executed the necessary "
            "authorized tools. "
            "Your job now is only to explain the verified "
            "tool results accurately. "
            "Never fabricate information."
        )

        final_response = self.model_provider.generate(
            ModelRequest(
                prompt=final_prompt,
                system_prompt=final_system_prompt,
            )
        )

        return final_response.text

    @staticmethod
    def _format_tool_result(
        tool_name: str,
        result: object,
    ) -> str:
        """
        Convert a REAL JARVIS tool result into text.

        This formatting is deterministic.

        The AI does not participate in this step,
        which prevents it from changing the raw data
        before the final answer is generated.
        """

        # A list is useful for directory contents.
        if isinstance(result, list):
            if not result:
                formatted_result = "(empty)"
            else:
                formatted_result = "\n".join(
                    f"- {item}"
                    for item in result
                )

        # A dictionary is useful for system information.
        elif isinstance(result, dict):
            if not result:
                formatted_result = "(empty)"
            else:
                formatted_result = "\n".join(
                    f"{key}: {value}"
                    for key, value in result.items()
                )

        # Strings and other simple objects can simply
        # be converted to text.
        else:
            formatted_result = str(result)

        return (
            f"Tool: {tool_name}\n"
            f"Verified result:\n"
            f"{formatted_result}"
        )