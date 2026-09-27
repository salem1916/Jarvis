import json

from jarvis.core.action_confirmation import (
    ActionConfirmationHandler,
    ActionConfirmationRequest,
    ActionDeclinedError,
)
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

    Model requests always remain untrusted.

    Execution path:

        Model
          ↓
        ToolRequest
          ↓
        ToolService
          ↓
        PermissionPolicy
          ↓
        ToolExecutor

    Actions requiring confirmation additionally become:

        ConfirmationRequiredError
          ↓
        trusted ActionConfirmationHandler
          ↓
        human approval
          ↓
        retry exact request with confirmed=True

    The model cannot generate the confirmed flag itself.
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
        confirmation_handler: ActionConfirmationHandler | None = None,
    ) -> str:
        """
        Execute one natural-language JARVIS request.

        Conversation changes are committed only after the
        complete request succeeds.
        """

        available_tools = [
            ModelToolDefinition(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters_schema,
            )
            for tool in self.tool_service.registry.tools()
        ]

        if conversation is not None:
            messages = conversation.snapshot()

        else:
            messages = []

        # -------------------------------------------------
        # Add trusted system instructions only once.
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

        messages.append(
            ModelMessage(
                role="user",
                content=prompt,
            )
        )

        tool_rounds_used = 0

        while True:
            response = self.model_provider.generate(
                ModelRequest(
                    prompt=prompt,
                    messages=messages,
                    tools=available_tools,
                )
            )

            messages.append(
                ModelMessage(
                    role="assistant",
                    content=response.text,
                    tool_calls=response.tool_calls,
                )
            )

            # No tool calls means the model produced
            # its final answer.
            if not response.tool_calls:
                if conversation is not None:
                    conversation.replace(
                        messages
                    )

                return response.text

            if tool_rounds_used >= self.max_tool_rounds:
                raise AgentLoopLimitError(
                    "JARVIS reached the maximum number "
                    "of tool rounds for this request."
                )

            for tool_call in response.tool_calls:
                request = ToolRequest(
                    tool_name=tool_call.name,
                    arguments=tool_call.arguments,
                )

                try:
                    result = self._execute_tool_request(
                        request=request,
                        confirmation_handler=confirmation_handler,
                    )

                    tool_content = self._serialize_tool_result(
                        result
                    )

                # =============================================
                # SECURITY FAILURES
                #
                # Never send these back to the model as a
                # recoverable observation.
                # =============================================

                except PermissionDeniedError:
                    raise

                except ConfirmationRequiredError:
                    raise

                except ActionDeclinedError:
                    raise

                # =============================================
                # NORMAL EXECUTION MISTAKES
                #
                # These may be corrected by another model turn.
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

                messages.append(
                    ModelMessage(
                        role="tool",
                        tool_name=tool_call.name,
                        content=tool_content,
                    )
                )

            tool_rounds_used += 1

    def _execute_tool_request(
        self,
        request: ToolRequest,
        confirmation_handler: ActionConfirmationHandler | None,
    ) -> object:
        """
        Execute one tool request with optional human approval.

        First execution uses normal policy enforcement.

        If confirmation is required:

            no handler
                -> propagate ConfirmationRequiredError

            handler rejects
                -> ActionDeclinedError

            handler approves
                -> execute the SAME request exactly once
                   with confirmed=True
        """

        try:
            return self.tool_service.execute(
                request
            )

        except ConfirmationRequiredError:
            if confirmation_handler is None:
                raise

            tool = self.tool_service.registry.get(
                request.tool_name
            )

            confirmation = ActionConfirmationRequest(
                tool_name=request.tool_name,
                capability=tool.required_capability,
                arguments=dict(
                    request.arguments
                ),
            )

            approved = confirmation_handler.confirm(
                confirmation
            )

            if not approved:
                raise ActionDeclinedError(
                    "The user declined the requested action."
                )

            # IMPORTANT:
            #
            # confirmed=True only retries this exact immediate
            # ToolRequest.
            #
            # ToolExecutor will STILL reject a DENY decision.
            return self.tool_service.execute(
                request,
                confirmed=True,
            )

    @staticmethod
    def _serialize_tool_result(
        result: object,
    ) -> str:
        """
        Convert successful tool output into model-friendly text.
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
        Convert a recoverable execution error into structured
        model feedback.
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