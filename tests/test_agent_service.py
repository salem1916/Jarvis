from pathlib import Path

import pytest

from jarvis.core.agent_service import AgentService
from jarvis.models.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelToolCall,
)
from jarvis.security.capabilities import Capability
from jarvis.security.policy import PermissionPolicy
from jarvis.tools.executor import (
    PermissionDeniedError,
    ToolExecutor,
)
from jarvis.tools.list_directory import ListDirectoryTool
from jarvis.tools.registry import ToolRegistry
from jarvis.tools.service import ToolService


class NormalResponseProvider(ModelProvider):
    """
    Fake AI provider used to test normal conversation.

    This model does not request any tool.
    """

    name = "test"

    def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        # The request is not needed for this simple fake model.
        del request

        return ModelResponse(
            text="Hello from JARVIS",
            provider=self.name,
            model="test-model",
        )


class ToolCallingProvider(ModelProvider):
    """
    Fake AI provider that always asks JARVIS
    to execute list_directory.

    The fake model itself does NOT execute anything.
    """

    name = "test"

    def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        # AgentService should have provided the model
        # with the registered JARVIS tools.
        assert request.tools

        return ModelResponse(
            text="",
            provider=self.name,
            model="test-model",
            tool_calls=[
                ModelToolCall(
                    name="list_directory",
                    arguments={
                        "path": ".",
                    },
                )
            ],
        )


def build_tool_service(
    workspace: Path,
    *,
    allow_read: bool,
) -> ToolService:
    """
    Build a real JARVIS ToolService for testing.

    This deliberately uses the real:
    - ToolRegistry
    - PermissionPolicy
    - ToolExecutor

    so our security tests exercise the same
    pipeline as the actual application.
    """

    registry = ToolRegistry()

    registry.register(
        ListDirectoryTool(
            workspace,
        )
    )

    allowed: set[Capability] = set()

    if allow_read:
        allowed.add(
            Capability.READ_FILE
        )

    policy = PermissionPolicy(
        allowed=allowed,
    )

    executor = ToolExecutor(
        policy,
    )

    return ToolService(
        registry,
        executor,
    )


def test_agent_returns_normal_model_response(
    tmp_path: Path,
) -> None:
    """
    If the AI does not request a tool,
    AgentService should return the normal AI response.
    """

    tool_service = build_tool_service(
        tmp_path,
        allow_read=True,
    )

    agent = AgentService(
        model_provider=NormalResponseProvider(),
        tool_service=tool_service,
    )

    result = agent.run(
        "Hello",
    )

    assert result == "Hello from JARVIS"


def test_agent_executes_requested_tool(
    tmp_path: Path,
) -> None:
    """
    If the AI requests list_directory,
    JARVIS should execute the REAL registered tool
    and return the REAL filesystem result.
    """

    file_path = (
        tmp_path / "hello.txt"
    )

    file_path.write_text(
        "Hello",
        encoding="utf-8",
    )

    tool_service = build_tool_service(
        tmp_path,
        allow_read=True,
    )

    agent = AgentService(
        model_provider=ToolCallingProvider(),
        tool_service=tool_service,
    )

    result = agent.run(
        "What files are in my workspace?",
    )

    # The result must come from the real temporary directory.
    assert "hello.txt" in result


def test_agent_cannot_bypass_permission_policy(
    tmp_path: Path,
) -> None:
    """
    Security test.

    Even if the AI asks for a valid tool,
    JARVIS must reject it when the capability
    is disabled.

    This proves that the AI cannot bypass
    PermissionPolicy.
    """

    tool_service = build_tool_service(
        tmp_path,
        allow_read=False,
    )

    agent = AgentService(
        model_provider=ToolCallingProvider(),
        tool_service=tool_service,
    )

    with pytest.raises(
        PermissionDeniedError,
    ):
        agent.run(
            "What files are in my workspace?",
        )