from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar

import pytest

from jarvis.core.action_confirmation import (
    ActionConfirmationRequest,
    ActionDeclinedError,
)
from jarvis.core.agent_service import AgentService
from jarvis.core.tool_request import ToolRequest
from jarvis.models.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelToolCall,
)
from jarvis.security.capabilities import Capability
from jarvis.security.policy import PermissionPolicy
from jarvis.tools.base import Tool
from jarvis.tools.executor import (
    ConfirmationRequiredError,
    PermissionDeniedError,
    ToolExecutor,
)
from jarvis.tools.registry import ToolRegistry
from jarvis.tools.service import ToolService


class ConfirmedActionTool(Tool):
    """
    Fake side-effect tool used only for confirmation tests.
    """

    name = "confirmed_action"

    description = (
        "Test action that requires explicit confirmation."
    )

    required_capability = Capability.WRITE_FILE

    parameters_schema: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
            },
        },
        "required": [
            "content",
        ],
        "additionalProperties": False,
    }

    def __init__(
        self,
    ) -> None:
        self.execution_count = 0

    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> object:
        self.execution_count += 1

        return {
            "written": arguments.get(
                "content"
            )
        }


class ConfirmationProvider(ModelProvider):
    """
    Fake model:

        first call
            -> request confirmed_action

        second call
            -> inspect real tool result
            -> return final answer
    """

    name = "test"

    def __init__(
        self,
    ) -> None:
        self.call_count = 0

    def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        self.call_count += 1

        if self.call_count == 1:
            return ModelResponse(
                text="",
                provider=self.name,
                model="test-model",
                tool_calls=[
                    ModelToolCall(
                        name="confirmed_action",
                        arguments={
                            "content": "hello",
                        },
                    )
                ],
            )

        assert any(
            message.role == "tool"
            and "hello" in message.content
            for message in request.messages
        )

        return ModelResponse(
            text="Action completed.",
            provider=self.name,
            model="test-model",
        )


class ApproveHandler:
    """
    Fake human that approves the request.
    """

    def __init__(
        self,
    ) -> None:
        self.requests: list[
            ActionConfirmationRequest
        ] = []

    def confirm(
        self,
        request: ActionConfirmationRequest,
    ) -> bool:
        self.requests.append(
            request
        )

        return True


class RejectHandler:
    """
    Fake human that explicitly rejects the request.
    """

    def confirm(
        self,
        request: ActionConfirmationRequest,
    ) -> bool:
        del request

        return False


def build_confirmation_service(
    tool: ConfirmedActionTool,
) -> ToolService:
    """
    Build a real secure tool pipeline whose WRITE_FILE
    capability requires human confirmation.
    """

    registry = ToolRegistry()

    registry.register(
        tool
    )

    policy = PermissionPolicy(
        require_confirmation={
            Capability.WRITE_FILE,
        }
    )

    executor = ToolExecutor(
        policy
    )

    return ToolService(
        registry,
        executor,
    )


def test_agent_executes_action_after_user_approval(
    tmp_path: Path,
) -> None:
    """
    Explicit human approval should allow exactly the
    requested confirmation-required action.
    """

    del tmp_path

    tool = ConfirmedActionTool()

    service = build_confirmation_service(
        tool
    )

    provider = ConfirmationProvider()

    handler = ApproveHandler()

    agent = AgentService(
        model_provider=provider,
        tool_service=service,
    )

    result = agent.run(
        "Perform the confirmed action.",
        confirmation_handler=handler,
    )

    assert result == "Action completed."

    assert tool.execution_count == 1

    assert provider.call_count == 2

    assert len(
        handler.requests
    ) == 1

    request = handler.requests[0]

    assert request.tool_name == "confirmed_action"

    assert request.capability is Capability.WRITE_FILE

    assert request.arguments == {
        "content": "hello",
    }


def test_user_can_decline_confirmation(
    tmp_path: Path,
) -> None:
    """
    Rejecting the confirmation must prevent execution.
    """

    del tmp_path

    tool = ConfirmedActionTool()

    agent = AgentService(
        model_provider=ConfirmationProvider(),
        tool_service=build_confirmation_service(
            tool
        ),
    )

    with pytest.raises(
        ActionDeclinedError,
    ):
        agent.run(
            "Perform the confirmed action.",
            confirmation_handler=RejectHandler(),
        )

    assert tool.execution_count == 0


def test_missing_handler_does_not_auto_approve(
    tmp_path: Path,
) -> None:
    """
    A confirmation-required action must never silently run
    when no trusted frontend is available to ask the user.
    """

    del tmp_path

    tool = ConfirmedActionTool()

    agent = AgentService(
        model_provider=ConfirmationProvider(),
        tool_service=build_confirmation_service(
            tool
        ),
    )

    with pytest.raises(
        ConfirmationRequiredError,
    ):
        agent.run(
            "Perform the confirmed action."
        )

    assert tool.execution_count == 0


def test_confirmed_flag_cannot_override_deny(
    tmp_path: Path,
) -> None:
    """
    CRITICAL SECURITY TEST.

    Even trusted confirmed=True cannot turn a DENY policy
    decision into ALLOW.
    """

    del tmp_path

    tool = ConfirmedActionTool()

    registry = ToolRegistry()

    registry.register(
        tool
    )

    # WRITE_FILE is neither allowed nor confirmation-required.
    # Therefore policy result is DENY.
    policy = PermissionPolicy()

    service = ToolService(
        registry,
        ToolExecutor(
            policy
        ),
    )

    request = ToolRequest(
        tool_name="confirmed_action",
        arguments={
            "content": "must not execute",
        },
    )

    with pytest.raises(
        PermissionDeniedError,
    ):
        service.execute(
            request,
            confirmed=True,
        )

    assert tool.execution_count == 0