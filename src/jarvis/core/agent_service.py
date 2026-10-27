import json
import re

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
from jarvis.security.capabilities import Capability
from jarvis.tools.executor import (
    ConfirmationRequiredError,
    PermissionDeniedError,
)
from jarvis.tools.selector import ToolSelector
from jarvis.tools.service import ToolService

# =========================================================
# TRUSTED AGENT EXECUTION POLICY
# =========================================================
#
# This policy is injected by trusted JARVIS code.
#
# It is not controlled by the model and is not stored as part
# of the ordinary user conversation.
#
# Core rule:
#
#     Observation is not execution.
#
# Looking at something does not mean that the requested action
# has actually happened.
# =========================================================

_AGENT_EXECUTION_POLICY = """
[JARVIS TRUSTED EXECUTION POLICY]

You are operating as an agent, not only as a chatbot.

When the user asks you to perform an action:

1. Continue working until the requested action has actually
   been executed, or until a real blocker prevents execution.

2. Observation tools do not complete side-effecting tasks.
   For example, listing UI controls does not satisfy a request
   to click a button.

3. Never claim that you opened, clicked, typed, saved, deleted,
   changed, sent, installed, deployed, or otherwise performed
   an action unless a trusted tool result from the CURRENT user
   request confirms that the action succeeded.

4. If an observation reveals the information needed for the
   next action, continue directly to the appropriate action
   tool instead of stopping to describe the observation.

5. Do not ask the user a follow-up question when the current
   environment and available tools already provide enough
   information to continue safely.

6. Tool errors are observations, not successful actions.
   Recover when possible by using the available tools.

7. Permission denials and declined confirmations are final
   security decisions. Do not attempt to bypass them.

8. Keep final responses grounded in actual tool results.
""".strip()


class AgentLoopLimitError(RuntimeError):
    """
    Raised when the model continues requesting tools beyond
    JARVIS's configured safety limit.
    """


class AgentIncompleteTaskError(RuntimeError):
    """
    Raised when the model repeatedly attempts to finish an
    action request without actually completing the required
    trusted side effect.

    Failing explicitly is safer than allowing the model to
    falsely claim success.
    """


class AgentService:
    """
    Secure multi-turn JARVIS agent.

    Model requests remain untrusted.

    Execution path:

        User request
            ↓
        trusted goal requirements
            ↓
        ToolSelector
            ↓
        selected tool definitions
            ↓
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
        trusted execution evidence
            ↓
        completion guard
            ↓
        final response

    The model decides what it wants to do.

    The trusted JARVIS core decides whether the requested
    action actually happened.
    """

    def __init__(
        self,
        model_provider: ModelProvider,
        tool_service: ToolService,
        max_tool_rounds: int = 5,
        max_completion_retries: int = 2,
        tool_selector: ToolSelector | None = None,
    ) -> None:
        if max_tool_rounds < 1:
            raise ValueError(
                "max_tool_rounds must be at least 1."
            )

        if max_completion_retries < 0:
            raise ValueError(
                "max_completion_retries cannot be negative."
            )

        self.model_provider = model_provider
        self.tool_service = tool_service
        self.max_tool_rounds = max_tool_rounds
        self.max_completion_retries = max_completion_retries

        self.tool_selector = (
            tool_selector
            or ToolSelector(
                tool_service.registry
            )
        )

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

        For recognized action requests, JARVIS records which
        trusted side-effect capabilities must succeed before
        the model is allowed to finish.
        """

        # =================================================
        # RELEVANT TOOL SELECTION
        # =================================================
        #
        # Instead of exposing every registered JARVIS tool to
        # the model for every request, expose the smallest
        # useful subset when we can identify the task.
        #
        # This reduces model prompt size and local-model
        # latency.
        #
        # ToolSelector is NOT a security boundary.
        # All execution still goes through ToolService.
        # =================================================

        selected_tools = self.tool_selector.select(
            prompt
        )

        available_tools = [
            ModelToolDefinition(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters_schema,
            )
            for tool in selected_tools
        ]

        if conversation is not None:
            messages = conversation.snapshot()

        else:
            messages = []

        # -------------------------------------------------
        # Add the product-level system prompt only once.
        # -------------------------------------------------

        has_system_message = any(
            message.role == "system"
            for message in messages
        )

        if system_prompt and has_system_message:
            # Preferences may change between turns; don't keep a stale memory snapshot.
            for message in messages:
                if message.role == "system":
                    message.content = system_prompt
                    break

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

        # =================================================
        # TRUSTED GOAL CONTRACT
        # =================================================
        #
        # The model does not get to decide by itself that an
        # explicit side-effecting request is complete.
        #
        # Example:
        #
        #     User:
        #         Click 7 in Calculator.
        #
        #     Required capability:
        #         CLICK_UI
        #
        # list_ui_elements may help the model discover the
        # button, but it cannot satisfy CLICK_UI.
        # =================================================

        required_capabilities = (
            self._infer_required_capabilities(
                prompt
            )
        )

        successful_capabilities: set[
            Capability
        ] = set()

        successful_tools: list[
            str
        ] = []

        tool_rounds_used = 0
        completion_retries_used = 0

        completion_feedback: str | None = None

        while True:
            response = self.model_provider.generate(
                ModelRequest(
                    prompt=prompt,
                    messages=self._build_model_messages(
                        messages=messages,
                        completion_feedback=completion_feedback,
                    ),
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

            # =================================================
            # MODEL WANTS TO FINISH
            # =================================================

            if not response.tool_calls:
                missing_capabilities = (
                    required_capabilities
                    - successful_capabilities
                )

                if missing_capabilities:
                    # The assistant's attempted final answer is
                    # not trustworthy because a required action
                    # has not actually happened.
                    #
                    # Remove that answer from working history.

                    messages.pop()

                    if (
                        completion_retries_used
                        >= self.max_completion_retries
                    ):
                        raise AgentIncompleteTaskError(
                            self._build_incomplete_task_error(
                                missing_capabilities=(
                                    missing_capabilities
                                ),
                                successful_tools=(
                                    successful_tools
                                ),
                            )
                        )

                    completion_retries_used += 1

                    completion_feedback = (
                        self._build_completion_feedback(
                            missing_capabilities=(
                                missing_capabilities
                            ),
                            successful_tools=(
                                successful_tools
                            ),
                        )
                    )

                    # Send the model back to work.
                    continue

                # ---------------------------------------------
                # The trusted goal requirements are satisfied.
                # ---------------------------------------------

                if conversation is not None:
                    conversation.replace(
                        messages
                    )

                return response.text

            # =================================================
            # MODEL REQUESTED TOOL EXECUTION
            # =================================================

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

                    # -----------------------------------------
                    # TRUSTED SUCCESS EVIDENCE
                    # -----------------------------------------
                    #
                    # A capability counts as completed only when
                    # the trusted tool actually returned
                    # successfully.
                    #
                    # A tool returning:
                    #
                    #     {"ok": False}
                    #
                    # explicitly does not count.
                    # -----------------------------------------

                    if self._result_is_successful(
                        result
                    ):
                        tool = self.tool_service.registry.get(
                            tool_call.name
                        )

                        successful_capabilities.add(
                            tool.required_capability
                        )

                        successful_tools.append(
                            tool_call.name
                        )

                # =============================================
                # SECURITY FAILURES
                # =============================================
                #
                # Security failures must escape immediately.
                #
                # IMPORTANT:
                #
                # PermissionDeniedError inherits through
                # PermissionError/OSError.
                #
                # Therefore these catches MUST appear before
                # generic OSError handling below.
                # =============================================

                except PermissionDeniedError:
                    raise

                except ConfirmationRequiredError:
                    raise

                except ActionDeclinedError:
                    raise

                # =============================================
                # RECOVERABLE EXECUTION ERRORS
                # =============================================
                #
                # These are returned to the model as observations
                # so it can potentially correct its request.
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
                        tool_call_id=tool_call.call_id,
                        content=tool_content,
                    )
                )

            tool_rounds_used += 1

            missing_after_round = (
                required_capabilities
                - successful_capabilities
            )

            if not missing_after_round:
                completion_feedback = None

    def _execute_tool_request(
        self,
        request: ToolRequest,
        confirmation_handler: ActionConfirmationHandler | None,
    ) -> object:
        """
        Execute one tool request with optional human approval.

        First execution uses normal policy enforcement.

        If confirmation is required:

            no confirmation handler
                -> propagate ConfirmationRequiredError

            user rejects
                -> ActionDeclinedError

            user approves
                -> execute the SAME ToolRequest exactly once
                   with confirmed=True

        The model cannot provide confirmed=True itself.
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
            # confirmed=True applies only to this exact,
            # immediate ToolRequest.
            #
            # ToolExecutor still rejects DENY decisions.

            return self.tool_service.execute(
                request,
                confirmed=True,
            )

    # =====================================================
    # TRUSTED MODEL MESSAGE CONSTRUCTION
    # =====================================================

    @staticmethod
    def _build_model_messages(
        messages: list[ModelMessage],
        completion_feedback: str | None,
    ) -> list[ModelMessage]:
        """
        Build the messages sent to the current model.

        Runtime execution policy is injected transiently.

        It is not persisted into Conversation history.
        """

        runtime_messages: list[
            ModelMessage
        ] = [
            ModelMessage(
                role="system",
                content=_AGENT_EXECUTION_POLICY,
            )
        ]

        if completion_feedback is not None:
            runtime_messages.append(
                ModelMessage(
                    role="system",
                    content=completion_feedback,
                )
            )

        system_messages = [
            message
            for message in messages
            if message.role == "system"
        ]

        conversation_messages = [
            message
            for message in messages
            if message.role != "system"
        ]

        return [
            *system_messages,
            *runtime_messages,
            *conversation_messages,
        ]

    # =====================================================
    # GOAL / COMPLETION INFERENCE
    # =====================================================

    @staticmethod
    def _infer_required_capabilities(
        prompt: str,
    ) -> frozenset[Capability]:
        """
        Infer simple explicit action requirements.

        This is deliberately conservative.

        It is not the final JARVIS planner.

        Its purpose is to prevent obvious false-completion
        behavior for commands such as:

            Click 7 in Calculator.
            Open Notepad.
            Close Discord.
            Type hello into Notepad.
            Save the document.
            Minimize Chrome.

        Complex workflows will later use structured task plans.
        """

        normalized = " ".join(
            prompt
            .strip()
            .casefold()
            .split()
        )

        if not normalized:
            return frozenset()

        # -------------------------------------------------
        # INFORMATIONAL QUESTIONS
        # -------------------------------------------------
        #
        # Merely discussing an action must not require the
        # action itself.
        #
        # Example:
        #
        #     How do I open Calculator?
        #
        # must not launch Calculator.
        # -------------------------------------------------

        informational_prefixes = (
            "what ",
            "why ",
            "how ",
            "which ",
            "where ",
            "when ",
            "who ",
            "explain ",
            "describe ",
            "tell me about ",
            "can you explain ",
            "could you explain ",
            "can you tell me how ",
            "could you tell me how ",
        )

        if normalized.startswith(
            informational_prefixes
        ):
            return frozenset()

        required: set[
            Capability
        ] = set()

        # -------------------------------------------------
        # STRUCTURED UI INTERACTION
        # -------------------------------------------------

        if re.search(
            r"\bclick\b",
            normalized,
        ):
            required.add(
                Capability.CLICK_UI
            )

        if re.search(
            r"\bpress\b.*\bbutton\b",
            normalized,
        ):
            required.add(
                Capability.CLICK_UI
            )

        # -------------------------------------------------
        # LITERAL TEXT ENTRY
        # -------------------------------------------------

        if re.search(
            r"\btype\b",
            normalized,
        ):
            required.add(
                Capability.TYPE_TEXT
            )

        if re.search(
            r"\benter\s+(?:the\s+)?text\b",
            normalized,
        ):
            required.add(
                Capability.TYPE_TEXT
            )

        # -------------------------------------------------
        # APPLICATION LAUNCHING
        # -------------------------------------------------

        if re.search(
            r"\b(open|launch)\b",
            normalized,
        ):
            required.add(
                Capability.OPEN_APPLICATION
            )

        # -------------------------------------------------
        # APPLICATION CLOSING
        # -------------------------------------------------

        if re.search(
            r"\b(close|quit)\b",
            normalized,
        ):
            required.add(
                Capability.CLOSE_APPLICATION
            )

        # -------------------------------------------------
        # WINDOW STATE CONTROL
        # -------------------------------------------------

        if re.search(
            (
                r"\b("
                r"minimize|"
                r"minimise|"
                r"maximize|"
                r"maximise|"
                r"restore|"
                r"focus"
                r")\b"
            ),
            normalized,
        ):
            required.add(
                Capability.CONTROL_APPLICATION
            )

        if re.search(
            r"\bbring\b.*\bfront\b",
            normalized,
        ):
            required.add(
                Capability.CONTROL_APPLICATION
            )

        # -------------------------------------------------
        # TRUSTED KEYBOARD ACTIONS
        # -------------------------------------------------

        if re.search(
            (
                r"\b("
                r"save|"
                r"copy|"
                r"paste|"
                r"undo|"
                r"redo"
                r")\b"
            ),
            normalized,
        ):
            required.add(
                Capability.KEYBOARD_ACTION
            )

        if "select all" in normalized:
            required.add(
                Capability.KEYBOARD_ACTION
            )

        if re.search(
            r"\bpress\s+(enter|escape|tab)\b",
            normalized,
        ):
            required.add(
                Capability.KEYBOARD_ACTION
            )

        # -------------------------------------------------
        # FILESYSTEM MODIFICATION
        # -------------------------------------------------

        if (
            "file" in normalized
            and re.search(
                r"\b(create|write|overwrite)\b",
                normalized,
            )
        ):
            required.add(
                Capability.WRITE_FILE
            )

        if (
            "file" in normalized
            and re.search(
                r"\b(delete|trash|remove)\b",
                normalized,
            )
        ):
            required.add(
                Capability.DELETE_FILE
            )

        # -------------------------------------------------
        # FUTURE EXTERNAL ACTIONS
        # -------------------------------------------------

        if re.search(
            r"\bsend\b.*\bemail\b",
            normalized,
        ):
            required.add(
                Capability.SEND_EMAIL
            )

        if re.search(
            r"\binstall\b",
            normalized,
        ):
            required.add(
                Capability.INSTALL_SOFTWARE
            )

        if re.search(
            r"\bdeploy\b",
            normalized,
        ):
            required.add(
                Capability.DEPLOY_APPLICATION
            )

        return frozenset(
            required
        )

    # =====================================================
    # COMPLETION GUARD FEEDBACK
    # =====================================================

    @staticmethod
    def _build_completion_feedback(
        missing_capabilities: set[Capability]
        | frozenset[Capability],
        successful_tools: list[str],
    ) -> str:
        """
        Trusted correction sent when the model tries to finish
        before the requested side effect happened.
        """

        missing = ", ".join(
            sorted(
                capability.value
                for capability
                in missing_capabilities
            )
        )

        successful = (
            ", ".join(
                successful_tools
            )
            if successful_tools
            else "none"
        )

        return (
            "[JARVIS EXECUTION GUARD]\n\n"
            "Your previous response attempted to finish the "
            "request before the requested action was actually "
            "completed.\n\n"
            f"Still required: {missing}\n"
            f"Successful tools so far: {successful}\n\n"
            "Continue the task now. Use observation tools only "
            "when needed to identify the target, then execute "
            "the appropriate side-effect tool. Do not claim "
            "success until the missing action has actually "
            "succeeded."
        )

    @staticmethod
    def _build_incomplete_task_error(
        missing_capabilities: set[Capability]
        | frozenset[Capability],
        successful_tools: list[str],
    ) -> str:
        """
        Return a trustworthy failure rather than accepting a
        hallucinated success.
        """

        missing = ", ".join(
            sorted(
                capability.value
                for capability
                in missing_capabilities
            )
        )

        successful = (
            ", ".join(
                successful_tools
            )
            if successful_tools
            else "none"
        )

        return (
            "JARVIS could not complete the requested action "
            "reliably. "
            f"Missing successful capabilities: {missing}. "
            f"Successful tools: {successful}."
        )

    # =====================================================
    # TOOL SUCCESS
    # =====================================================

    @staticmethod
    def _result_is_successful(
        result: object,
    ) -> bool:
        """
        Decide whether a normally returned tool result counts
        as trusted success evidence.

        Most tools signal failure by raising an exception.

        This additionally protects against a tool explicitly
        returning:

            {"ok": False}
        """

        return not (
            isinstance(
                result,
                dict,
            )
            and result.get(
                "ok"
            )
            is False
        )

    # =====================================================
    # TOOL SERIALIZATION
    # =====================================================

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

        payload: dict[
            str,
            object,
        ] = {
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
