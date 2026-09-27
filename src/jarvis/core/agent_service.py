import json

from jarvis.core.conversation import Conversation
from jarvis.core.tool_request import ToolRequest
from jarvis.models.base import (
    ModelMessage,
    ModelProvider,
    ModelRequest,
    ModelToolDefinition,
)
from jarvis.tools.executor import (
    ConfirmationRequiredError,
    PermissionDeniedError,
)
from jarvis.tools.service import ToolService


class AgentLoopLimitError(RuntimeError):
    """
    Raised when the model continues requesting tools beyond
    JARVIS's configured safety limit.
    """


class AgentService:
    """
    Secure multi-turn JARVIS agent.

    The model may REQUEST actions, but it never receives
    direct authority over the computer.

    Every action still passes through:

        Model
          ↓
        ToolRequest
          ↓
        ToolService
          ↓
        PermissionPolicy
          ↓
        ToolExecutor
          ↓
        Tool

    Recoverable execution failures may be returned to the
    model so it can correct mistakes.

    Security decisions are NEVER recoverable by the model.
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

        Conversation history is committed only when the
        complete request succeeds.

        This prevents failed requests from leaving a
        half-completed conversation behind.
        """

        # -------------------------------------------------
        # Build the provider-independent tool definitions
        # exposed to the model.
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
        # Start from previous conversation history if one
        # exists.
        # -------------------------------------------------

        if conversation is not None:
            messages = conversation.snapshot()

        else:
            messages = []

        # -------------------------------------------------
        # Add the trusted system prompt only once.
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
            # -------------------------------------------------
            # Ask the model what to do next.
            # -------------------------------------------------

            response = self.model_provider.generate(
                ModelRequest(
                    prompt=prompt,
                    messages=messages,
                    tools=available_tools,
                )
            )

            # Preserve the assistant's exact response and
            # requested tool calls.
            messages.append(
                ModelMessage(
                    role="assistant",
                    content=response.text,
                    tool_calls=response.tool_calls,
                )
            )

            # -------------------------------------------------
            # No tool calls = final answer.
            # -------------------------------------------------

            if not response.tool_calls:
                if conversation is not None:
                    conversation.replace(
                        messages
                    )

                return response.text

            # -------------------------------------------------
            # Infinite-loop protection.
            # -------------------------------------------------

            if tool_rounds_used >= self.max_tool_rounds:
                raise AgentLoopLimitError(
                    "JARVIS reached the maximum number "
                    "of tool rounds for this request."
                )

            # -------------------------------------------------
            # Execute every requested tool.
            # -------------------------------------------------

            for tool_call in response.tool_calls:
                request = ToolRequest(
                    tool_name=tool_call.name,
                    arguments=tool_call.arguments,
                )

                try:
                    result = self.tool_service.execute(
                        request
                    )

                    tool_content = self._serialize_tool_result(
                        result
                    )

                # =============================================
                # SECURITY EXCEPTIONS
                #
                # These MUST escape immediately.
                #
                # The AI is never allowed to reason around,
                # retry around, or reinterpret a security
                # denial.
                # =============================================

                except PermissionDeniedError:
                    raise

                except ConfirmationRequiredError:
                    raise

                # =============================================
                # RECOVERABLE EXECUTION ERRORS
                #
                # Examples:
                #
                # - wrong file path
                # - missing directory
                # - invalid calculator expression
                # - malformed tool argument
                #
                # These are returned to the model so it gets
                # another opportunity to correct its mistake.
                # =============================================

                except (
                    OSError,
                    TypeError,
                    ValueError,
                ) as exc:
                    tool_content = self._serialize_tool_error(
                        tool_name=tool_call.name,
                        error=exc,
                    )

                # -------------------------------------------------
                # Return either the real result or the recoverable
                # error as a native tool message.
                # -------------------------------------------------

                messages.append(
                    ModelMessage(
                        role="tool",
                        tool_name=tool_call.name,
                        content=tool_content,
                    )
                )

            tool_rounds_used += 1

    @staticmethod
    def _serialize_tool_result(
        result: object,
    ) -> str:
        """
        Convert successful tool output into text suitable
        for the model conversation.
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

        return str(
            result
        )

    @staticmethod
    def _serialize_tool_error(
        tool_name: str,
        error: Exception,
    ) -> str:
        """
        Convert a RECOVERABLE execution error into structured
        tool feedback.

        Important:

        PermissionDeniedError and
        ConfirmationRequiredError never reach this method.
        """

        payload: dict[str, object] = {
            "ok": False,
            "tool": tool_name,
            "error": {
                "type": type(
                    error
                ).__name__,
                "message": str(
                    error
                ),
            },
        }

        # Filesystem mistakes get an additional hint telling
        # the model how to discover the real approved paths.
        if tool_name in {
            "read_file",
            "list_directory",
        }:
            payload["recovery_hint"] = (
                "The filesystem path may be wrong. "
                "Use list_filesystem_scopes to discover "
                "the exact approved filesystem locations, "
                "then retry with the correct path."
            )

        return json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )