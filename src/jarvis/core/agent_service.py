import json

from jarvis.core.conversation import Conversation
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
    Raised when the model continues requesting tools
    beyond JARVIS's configured safety limit.
    """


class AgentService:
    """
    Secure multi-turn JARVIS agent.

    Architecture:

        User
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
        Real result
          ↓
        role="tool"
          ↓
        Model continues

    A Conversation object can now preserve this history
    across several separate user requests.
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
        conversation: Conversation | None = None,
    ) -> str:
        """
        Execute one natural-language JARVIS request.

        If a Conversation is supplied, previous successful
        messages are included.

        This means separate calls such as:

            "What files do I have?"

        followed by:

            "What does it contain?"

        can share context.

        Conversation changes are committed only after
        successful completion.
        """

        # -------------------------------------------------
        # REAL tools registered in JARVIS
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
        # Start from previous conversation history.
        #
        # We work on a COPY.
        #
        # If the request later crashes or is denied,
        # the original conversation remains unchanged.
        # -------------------------------------------------

        if conversation is not None:
            messages = conversation.snapshot()
        else:
            messages = []

        # -------------------------------------------------
        # Add the system prompt once.
        #
        # We do not want to duplicate it on every
        # separate "ask" command.
        # -------------------------------------------------

        has_system_message = any(
            message.role == "system"
            for message in messages
        )

        if (
            system_prompt
            and not has_system_message
        ):
            messages.insert(
                0,
                ModelMessage(
                    role="system",
                    content=system_prompt,
                ),
            )

        # -------------------------------------------------
        # Add the new user request.
        # -------------------------------------------------

        messages.append(
            ModelMessage(
                role="user",
                content=prompt,
            )
        )

        tool_rounds_used = 0

        while True:
            # ---------------------------------------------
            # Send the FULL conversation to the model.
            # ---------------------------------------------

            response = self.model_provider.generate(
                ModelRequest(
                    # Kept for compatibility with our
                    # provider-independent model API.
                    prompt=prompt,

                    messages=messages,

                    tools=available_tools,
                )
            )

            # ---------------------------------------------
            # Preserve the assistant's exact response
            # and any tool calls it requested.
            # ---------------------------------------------

            messages.append(
                ModelMessage(
                    role="assistant",
                    content=response.text,
                    tool_calls=response.tool_calls,
                )
            )

            # ---------------------------------------------
            # No tool call means the request is complete.
            # ---------------------------------------------

            if not response.tool_calls:
                # Only now do we commit the completed
                # conversation state.
                if conversation is not None:
                    conversation.replace(
                        messages
                    )

                return response.text

            # ---------------------------------------------
            # Infinite-loop protection.
            # ---------------------------------------------

            if tool_rounds_used >= self.max_tool_rounds:
                raise AgentLoopLimitError(
                    "JARVIS reached the maximum number "
                    "of tool rounds for this request."
                )

            # ---------------------------------------------
            # Execute model-requested tools.
            #
            # They still go through the REAL security
            # pipeline.
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
                # Add the verified result to conversation
                # history as a native tool message.
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
        Convert real tool results into model-friendly text.

        Lists and dictionaries become JSON.

        Plain strings, such as file contents, remain
        plain strings.
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