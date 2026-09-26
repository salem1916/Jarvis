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
    Fake model for normal conversation.

    It never requests a tool.
    """

    name = "test"

    def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        del request

        return ModelResponse(
            text="Hello from JARVIS",
            provider=self.name,
            model="test-model",
        )


class ToolCallingProvider(ModelProvider):
    """
    Fake model that behaves like a tiny agent.

    First model call:
        requests list_directory.

    Second model call:
        receives the REAL tool result and produces
        the final natural-language response.
    """

    name = "test"

    def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        # -------------------------------------------------
        # FIRST CALL
        #
        # Tools are present, so behave like the model
        # deciding which JARVIS tool it needs.
        # -------------------------------------------------

        if request.tools:
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

        # -------------------------------------------------
        # SECOND CALL
        #
        # There are no tools now.
        #
        # The agent should have inserted the REAL result
        # into this final request.
        # -------------------------------------------------

        assert "hello.txt" in request.prompt

        return ModelResponse(
            text=(
                "Your workspace contains "
                "the file hello.txt."
            ),
            provider=self.name,
            model="test-model",
        )


def build_tool_service(
    workspace: Path,
    *,
    allow_read: bool,
) -> ToolService:
    """
    Build a real JARVIS ToolService.

    These tests use the actual:
    - ToolRegistry
    - PermissionPolicy
    - ToolExecutor

    instead of bypassing the security architecture.
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
    Normal conversation should still work without
    using any tools.
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


def test_agent_executes_tool_and_returns_final_answer(
    tmp_path: Path,
) -> None:
    """
    Full agent flow:

    natural language
        -> model chooses tool
        -> real tool executes
        -> real result returned
        -> model produces final answer
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

    assert result == (
        "Your workspace contains "
        "the file hello.txt."
    )


def test_agent_cannot_bypass_permission_policy(
    tmp_path: Path,
) -> None:
    """
    Security test.

    Even though the AI requests list_directory,
    execution must fail when READ_FILE permission
    is disabled.
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