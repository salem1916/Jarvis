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
    Fake AI provider for normal conversation.

    It answers immediately and does not request
    any JARVIS tools.
    """

    name = "test"

    def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        # This fake provider does not need to inspect
        # the request.
        del request

        return ModelResponse(
            text="Hello from JARVIS",
            provider=self.name,
            model="test-model",
        )


class MultiStepProvider(ModelProvider):
    """
    Fake AI provider that simulates a real
    multi-step JARVIS agent.

    Round 1:
        list_directory

    Round 2:
        after discovering hello.txt,
        request read_file

    Round 3:
        after receiving the real contents,
        answer the user.
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
        # MODEL CALL 1
        #
        # The model does not know which files exist yet.
        # It chooses list_directory.
        # ---------------------------------------------

        if self.call_count == 1:
            # AgentService should have supplied
            # JARVIS's available tools.
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
        # MODEL CALL 2
        #
        # JARVIS should now have executed
        # list_directory and shown the real filename
        # to the model.
        # ---------------------------------------------

        if self.call_count == 2:
            assert "hello.txt" in request.prompt

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
        # MODEL CALL 3
        #
        # JARVIS should now have executed read_file.
        #
        # The actual contents must appear in the
        # verified tool results supplied to the model.
        # ---------------------------------------------

        assert "Hello from the real file" in request.prompt

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
    Fake AI provider used for the permission test.

    It requests list_directory.

    When READ_FILE is disabled, JARVIS must reject
    this request before the model gets another turn.
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
    Fake broken AI provider.

    It deliberately requests the same tool forever.

    JARVIS must detect this and stop the loop.
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
    Build the real JARVIS tool/security pipeline
    for the tests.

    We deliberately use the real:

        ToolRegistry
            ↓
        PermissionPolicy
            ↓
        ToolExecutor
            ↓
        Tools

    so our tests do not bypass the architecture.
    """

    registry = ToolRegistry()

    # Register the two tools needed for our
    # multi-step test.
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
    A normal conversation should still work
    without executing any tools.
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


def test_agent_executes_multiple_tool_rounds(
    tmp_path: Path,
) -> None:
    """
    Test the complete multi-step agent flow.

    User request
        ↓
    AI chooses list_directory
        ↓
    JARVIS executes it
        ↓
    AI sees hello.txt
        ↓
    AI chooses read_file
        ↓
    JARVIS executes it
        ↓
    AI sees the real file contents
        ↓
    final answer
    """

    file_path = (
        tmp_path / "hello.txt"
    )

    file_path.write_text(
        "Hello from the real file",
        encoding="utf-8",
    )

    provider = MultiStepProvider()

    tool_service = build_tool_service(
        tmp_path,
        allow_read=True,
    )

    agent = AgentService(
        model_provider=provider,
        tool_service=tool_service,
    )

    result = agent.run(
        "Find a text file and tell me what it contains.",
    )

    assert result == (
        "The file says: "
        "Hello from the real file"
    )

    # There should have been exactly:
    #
    # 1. choose list_directory
    # 2. choose read_file
    # 3. produce final answer
    assert provider.call_count == 3


def test_agent_cannot_bypass_permission_policy(
    tmp_path: Path,
) -> None:
    """
    Security test.

    Even though the AI asks for a legitimate tool,
    JARVIS must refuse execution when READ_FILE
    permission is disabled.

    The model cannot bypass PermissionPolicy.
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


def test_agent_stops_infinite_tool_loop(
    tmp_path: Path,
) -> None:
    """
    Safety test.

    A broken or confused model must not be able
    to execute tools forever.

    We deliberately limit this agent to two
    tool rounds.
    """

    tool_service = build_tool_service(
        tmp_path,
        allow_read=True,
    )

    agent = AgentService(
        model_provider=EndlessToolProvider(),
        tool_service=tool_service,
        max_tool_rounds=2,
    )

    with pytest.raises(
        AgentLoopLimitError,
        match="maximum number of tool rounds",
    ):
        agent.run(
            "Keep listing the directory forever.",
        )