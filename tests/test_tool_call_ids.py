from typing import ClassVar, cast

from jarvis.core.agent_service import AgentService
from jarvis.core.tool_request import ToolRequest
from jarvis.models.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelToolCall,
)
from jarvis.security.capabilities import Capability
from jarvis.tools.service import ToolService


class FakeTool:
    name = "fake_action"

    description = (
        "Perform a fake action."
    )

    parameters_schema: ClassVar[
        dict[
            str,
            object,
        ]
    ] = {
        "type": "object",
        "properties": {},
    }

    required_capability = (
        Capability.CALCULATE
    )


class FakeRegistry:
    def __init__(
        self,
    ) -> None:
        self.tool = FakeTool()

    def tools(
        self,
    ) -> tuple[
        FakeTool,
        ...,
    ]:
        return (
            self.tool,
        )

    def get(
        self,
        name: str,
    ) -> FakeTool:
        if name != self.tool.name:
            raise KeyError(
                name
            )

        return self.tool


class FakeToolService:
    def __init__(
        self,
    ) -> None:
        self.registry = FakeRegistry()

    def execute(
        self,
        request: ToolRequest,
        *,
        confirmed: bool = False,
    ) -> object:
        del confirmed

        assert (
            request.tool_name
            == "fake_action"
        )

        return {
            "ok": True,
        }


class ToolCallIdProvider(
    ModelProvider
):
    name = "fake"

    def __init__(
        self,
    ) -> None:
        self.calls = 0

    def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        self.calls += 1

        if self.calls == 1:
            return ModelResponse(
                text="",
                provider=self.name,
                model="fake-model",
                tool_calls=[
                    ModelToolCall(
                        call_id="call-123",
                        name="fake_action",
                        arguments={},
                    )
                ],
            )

        tool_messages = [
            message
            for message
            in request.messages
            if message.role
            == "tool"
        ]

        assert tool_messages

        latest_tool_message = (
            tool_messages[-1]
        )

        assert (
            latest_tool_message.tool_name
            == "fake_action"
        )

        assert (
            latest_tool_message.tool_call_id
            == "call-123"
        )

        return ModelResponse(
            text="Done.",
            provider=self.name,
            model="fake-model",
        )


def test_agent_preserves_tool_call_id() -> None:
    provider = ToolCallIdProvider()

    tool_service = FakeToolService()

    service = AgentService(
        model_provider=provider,
        tool_service=cast(
            ToolService,
            tool_service,
        ),
    )

    result = service.run(
        "Use the fake action."
    )

    assert result == "Done."

    assert provider.calls == 2