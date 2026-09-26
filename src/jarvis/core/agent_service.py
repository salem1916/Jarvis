import json

from jarvis.core.tool_request import ToolRequest
from jarvis.models.base import (
    ModelMessage,
    ModelProvider,
    ModelRequest,
    ModelToolDefinition,
)
from jarvis.tools.service import ToolService


class AgentLoopLimitError(RuntimeError):
    """
    Raised when an AI keeps requesting tools for too long.

    This prevents accidental infinite execution loops.
    """


class AgentService:
    """
    Secure multi-turn JARVIS agent.

    Architecture:

        Salem
          ↓
        Model
          ↓
        ModelToolCall
          ↓
        ToolRequest
          ↓
        ToolService
          ↓
        PermissionPolicy
          ↓
        ToolExecutor
          ↓
        REAL tool result
          ↓
        role="tool" message
          ↓
        Model continues reasoning

    The model never directly executes computer actions.
    """

    def __init__(
        self,
        model_provider: ModelProvider,
        tool_service: ToolService,
        max_tool_rounds: int = 5,
    ) -> None:
        if max_tool_rounds < 1:
            raise ValueError(
                "max_tool_rounds must be at least 1."
            )

        self.model_provider = model_provider
        self.tool_service = tool_service
        self.max_tool_rounds = max_tool_rounds

    def run(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        """
        Execute one natural-language JARVIS request.

        Unlike the old implementation, we preserve the
        real model/tool conversation instead of rebuilding
        a textual prompt after each tool call.
        """

        # -------------------------------------------------
        # Expose only REAL registered JARVIS tools.
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
        # Build real conversation history.
        # -------------------------------------------------

        messages: list[ModelMessage] = []

        if system_prompt:
            messages.append(
                ModelMessage(
                    role="system",
                    content=system_prompt,
                )
            )

        messages.append(
            ModelMessage(
                role="user",
                content=prompt,
            )
        )

        tool_rounds_used = 0

        while True:
            # ---------------------------------------------
            # Give the model the COMPLETE conversation:
            #
            # system
            # user
            # previous assistant tool calls
            # previous real tool results
            # ---------------------------------------------

            response = self.model_provider.generate(
                ModelRequest(
                    # Kept for compatibility with our generic
                    # ModelRequest API.
                    prompt=prompt,

                    messages=messages,

                    tools=available_tools,
                )
            )

            # ---------------------------------------------
            # Save the assistant response itself.
            #
            # This is important because Ollama's next turn
            # needs to see which tools the assistant asked for.
            # ---------------------------------------------

            messages.append(
                ModelMessage(
                    role="assistant",
                    content=response.text,
                    tool_calls=response.tool_calls,
                )
            )

            # ---------------------------------------------
            # No tool requests means the agent is finished.
            # ---------------------------------------------

            if not response.tool_calls:
                return response.text

            # ---------------------------------------------
            # Safety limit BEFORE another execution round.
            # ---------------------------------------------

            if tool_rounds_used >= self.max_tool_rounds:
                raise AgentLoopLimitError(
                    "JARVIS reached the maximum number "
                    "of tool rounds for this request."
                )

            # ---------------------------------------------
            # Execute every requested tool through the
            # existing trusted JARVIS security pipeline.
            # ---------------------------------------------

            for tool_call in response.tool_calls:
                tool_request = ToolRequest(
                    tool_name=tool_call.name,
                    arguments=tool_call.arguments,
                )

                result = self.tool_service.execute(
                    tool_request
                )

                # -----------------------------------------
                # Add the REAL tool result as an actual
                # role="tool" message.
                #
                # The model now knows:
                #
                # "I requested list_directory and THIS
                # was the actual result."
                #
                # rather than receiving a rewritten prompt.
                # -----------------------------------------

                messages.append(
                    ModelMessage(
                        role="tool",
                        tool_name=tool_call.name,
                        content=self._serialize_tool_result(
                            result
                        ),
                    )
                )

            tool_rounds_used += 1

    @staticmethod
    def _serialize_tool_result(
        result: object,
    ) -> str:
        """
        Serialize REAL tool results deterministically.

        Lists and dictionaries become JSON so the model
        receives clear structured data.

        File contents and other strings remain unchanged.

        Tool output is still considered untrusted DATA.
        The system prompt tells the model not to obey
        instructions found inside tool results.
        """

        if isinstance(
            result,
            (list, dict),
        ):
            return json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
                default=str,
            )

        return str(result)