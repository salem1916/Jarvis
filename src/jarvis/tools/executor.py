from collections.abc import Mapping

from jarvis.security.policy import (
    PermissionDecision,
    PermissionPolicy,
)
from jarvis.tools.base import Tool


class PermissionDeniedError(PermissionError):
    """
    Raised when JARVIS security policy denies an action.
    """


class ConfirmationRequiredError(PermissionError):
    """
    Raised when an action requires explicit human approval.
    """


class ToolExecutor:
    """
    Final trusted execution gate for JARVIS tools.

    AI models never call Tool.execute() directly.

    Every tool invocation reaches this class after passing
    through ToolService.

    The `confirmed` flag is trusted application state.

    It is NOT part of a model tool schema, so the AI cannot
    approve its own actions.
    """

    def __init__(
        self,
        policy: PermissionPolicy,
    ) -> None:
        self.policy = policy

    def execute(
        self,
        tool: Tool,
        arguments: Mapping[str, object],
        *,
        confirmed: bool = False,
    ) -> object:
        """
        Execute one tool after enforcing its capability.

        DENY:
            Always stop.

        REQUIRE_CONFIRMATION:
            Stop unless the trusted application layer has
            already received explicit approval for this exact
            immediate request.

        ALLOW:
            Execute normally.
        """

        decision = self.policy.evaluate(
            tool.required_capability
        )

        # A confirmation can NEVER override DENY.
        if decision is PermissionDecision.DENY:
            raise PermissionDeniedError(
                "Permission denied for capability: "
                f"{tool.required_capability}"
            )

        if (
            decision
            is PermissionDecision.REQUIRE_CONFIRMATION
            and not confirmed
        ):
            raise ConfirmationRequiredError(
                "Confirmation required for capability: "
                f"{tool.required_capability}"
            )

        return tool.execute(
            arguments
        )