from collections.abc import Mapping

from jarvis.security.policy import PermissionDecision, PermissionPolicy
from jarvis.tools.base import Tool


class PermissionDeniedError(PermissionError):
    pass


class ConfirmationRequiredError(PermissionError):
    pass


class ToolExecutor:
    def __init__(self, policy: PermissionPolicy) -> None:
        self.policy = policy

    def execute(
        self,
        tool: Tool,
        arguments: Mapping[str, object],
    ) -> object:
        decision = self.policy.evaluate(tool.required_capability)

        if decision == PermissionDecision.DENY:
            raise PermissionDeniedError(
                f"Capability {tool.required_capability} is denied."
            )

        if decision == PermissionDecision.REQUIRE_CONFIRMATION:
            raise ConfirmationRequiredError(
                f"Capability {tool.required_capability} requires confirmation."
            )

        return tool.execute(arguments)