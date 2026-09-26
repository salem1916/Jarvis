from pathlib import Path

import pytest

from jarvis.core.agent_service import (
    AgentLoopLimitError,
    AgentService,
)
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
from jarvis.tools.read_file import ReadFileTool
from jarvis.tools.registry import ToolRegistry
from jarvis.tools.service import ToolService


class NormalResponseProvider(ModelProvider):
    """
    Fake model that answers without tools.
    """

    name = "test"

    def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        # A normal request should contain the user's
        # message in the conversation history.
        assert request.messages

        return ModelResponse(
            text="Hello from JARVIS",
            provider=self.name,
            model="test-model",
        )


class MultiStepProvider(ModelProvider):
    """
    Fake model that simulates:

        list_directory
            ↓
        read_file
            ↓
        final answer

    using REAL multi-turn tool history.
    """

    name = "test"

    def __init__(self) -> None:
        self.call_count = 0

    def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        self.call_count += 1

        # ---------------------------------------------
        # ROUND 1
        #
        # No tool result exists yet.
        # Discover available files.
        # ---------------------------------------------

        if self.call_count == 1:
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

        # ---------------------------------------------
        # ROUND 2
        #
        # AgentService must have added a REAL role="tool"
        # message containing hello.txt.
        # ---------------------------------------------

        if self.call_count == 2:
            tool_messages = [
                message
                for message in request.messages
                if message.role == "tool"
            ]

            assert tool_messages

            assert any(
                "hello.txt" in message.content
                for message in tool_messages
            )

            return ModelResponse(
                text="",
                provider=self.name,
                model="test-model",
                tool_calls=[
                    ModelToolCall(
                        name="read_file",
                        arguments={
                            "path": "hello.txt",
                        },
                    )
                ],
            )

        # ---------------------------------------------
        # ROUND 3
        #
        # A second role="tool" message must now contain
        # the actual contents of hello.txt.
        # ---------------------------------------------

        tool_messages = [
            message
            for message in request.messages
            if message.role == "tool"
        ]

        assert any(
            "Hello from the real file" in message.content
            for message in tool_messages
        )

        return ModelResponse(
            text=(
                "The file says: "
                "Hello from the real file"
            ),
            provider=self.name,
            model="test-model",
        )


class ToolCallingProvider(ModelProvider):
    """
    Fake model for permission enforcement testing.
    """

    name = "test"

    def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
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


class EndlessToolProvider(ModelProvider):
    """
    Broken model that requests a tool forever.

    JARVIS must stop it.
    """

    name = "test"

    def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
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
    Build the real JARVIS security/tool pipeline.
    """

    registry = ToolRegistry()

    registry.register(
        ListDirectoryTool(
            workspace,
        )
    )

    registry.register(
        ReadFileTool(
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
    Normal chat works without tool execution.
    """

    agent = AgentService(
        model_provider=NormalResponseProvider(),
        tool_service=build_tool_service(
            tmp_path,
            allow_read=True,
        ),
    )

    result = agent.run(
        "Hello",
    )

    assert result == "Hello from JARVIS"


def test_agent_executes_multiple_tool_rounds(
    tmp_path: Path,
) -> None:
    """
    Test native multi-turn agent flow:

        model
          ↓
        list_directory
          ↓
        tool message
          ↓
        model
          ↓
        read_file
          ↓
        tool message
          ↓
        final answer
    """

    (
        tmp_path / "hello.txt"
    ).write_text(
        "Hello from the real file",
        encoding="utf-8",
    )

    provider = MultiStepProvider()

    agent = AgentService(
        model_provider=provider,
        tool_service=build_tool_service(
            tmp_path,
            allow_read=True,
        ),
    )

    result = agent.run(
        "Find a text file and tell me what it contains."
    )

    assert result == (
        "The file says: "
        "Hello from the real file"
    )

    assert provider.call_count == 3


def test_agent_cannot_bypass_permission_policy(
    tmp_path: Path,
) -> None:
    """
    Tool requests must still obey PermissionPolicy.
    """

    agent = AgentService(
        model_provider=ToolCallingProvider(),
        tool_service=build_tool_service(
            tmp_path,
            allow_read=False,
        ),
    )

    with pytest.raises(
        PermissionDeniedError,
    ):
        agent.run(
            "What files are in my workspace?"
        )


def test_agent_stops_infinite_tool_loop(
    tmp_path: Path,
) -> None:
    """
    A broken model cannot execute tools forever.
    """

    agent = AgentService(
        model_provider=EndlessToolProvider(),
        tool_service=build_tool_service(
            tmp_path,
            allow_read=True,
        ),
        max_tool_rounds=2,
    )

    with pytest.raises(
        AgentLoopLimitError,
        match="maximum number of tool rounds",
    ):
        agent.run(
            "Keep listing forever."
        )