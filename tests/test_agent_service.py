from pathlib import Path

import pytest

from jarvis.core.agent_service import (
    AgentLoopLimitError,
    AgentService,
)
from jarvis.core.conversation import Conversation
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

# ---------------------------------------------------------
# FAKE MODEL 1
# Normal conversation with no tool calls
# ---------------------------------------------------------


class NormalResponseProvider(ModelProvider):
    """
    Fake AI model used to test normal conversation.

    It answers immediately without requesting any tool.
    """

    name = "test"

    def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        # AgentService should provide conversation messages.
        assert request.messages

        return ModelResponse(
            text="Hello from JARVIS",
            provider=self.name,
            model="test-model",
        )


# ---------------------------------------------------------
# FAKE MODEL 2
# Multi-step tool use inside ONE user request
# ---------------------------------------------------------


class MultiStepProvider(ModelProvider):
    """
    Fake AI model that simulates a real multi-step agent.

    Round 1:
        request list_directory

    Round 2:
        see hello.txt
        request read_file

    Round 3:
        see the real file contents
        produce the final answer
    """

    name = "test"

    def __init__(self) -> None:
        self.call_count = 0

    def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        self.call_count += 1

        # -------------------------------------------------
        # MODEL CALL 1
        #
        # The model does not know which files exist yet.
        # It requests list_directory.
        # -------------------------------------------------

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

        # -------------------------------------------------
        # MODEL CALL 2
        #
        # JARVIS should now have returned hello.txt
        # through a REAL role="tool" message.
        # -------------------------------------------------

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

        # -------------------------------------------------
        # MODEL CALL 3
        #
        # JARVIS should now have returned the REAL
        # contents of hello.txt.
        # -------------------------------------------------

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


# ---------------------------------------------------------
# FAKE MODEL 3
# Used to verify PermissionPolicy cannot be bypassed
# ---------------------------------------------------------


class ToolCallingProvider(ModelProvider):
    """
    Fake AI that always requests list_directory.

    The security test disables READ_FILE.

    Therefore JARVIS must reject this request before
    the AI gets another turn.
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


# ---------------------------------------------------------
# FAKE MODEL 4
# Used to test infinite-loop protection
# ---------------------------------------------------------


class EndlessToolProvider(ModelProvider):
    """
    Fake broken AI model.

    It requests list_directory every time forever.

    JARVIS must stop it using max_tool_rounds.
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


# ---------------------------------------------------------
# FAKE MODEL 5
# Conversation history across TWO separate user requests
# ---------------------------------------------------------


class ConversationHistoryProvider(ModelProvider):
    """
    Fake AI used to prove that conversation context survives
    across separate AgentService.run() calls.

    First user request:

        "What files do I have?"

    JARVIS:
        list_directory
        -> hello.txt
        -> "You have hello.txt."

    Second user request:

        "What does it contain?"

    The model must still know that "it" refers to hello.txt.

    Then:

        read_file("hello.txt")
        -> real file contents
        -> final answer
    """

    name = "test"

    def __init__(self) -> None:
        self.call_count = 0

    def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        self.call_count += 1

        # -------------------------------------------------
        # CALL 1
        #
        # First user request.
        #
        # Discover which files exist.
        # -------------------------------------------------

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

        # -------------------------------------------------
        # CALL 2
        #
        # Same user request, second model turn.
        #
        # JARVIS should now have provided hello.txt
        # as a real tool result.
        # -------------------------------------------------

        if self.call_count == 2:
            assert any(
                message.role == "tool"
                and "hello.txt" in message.content
                for message in request.messages
            )

            return ModelResponse(
                text="You have hello.txt.",
                provider=self.name,
                model="test-model",
            )

        # -------------------------------------------------
        # CALL 3
        #
        # SECOND SEPARATE user request:
        #
        # "What does it contain?"
        #
        # The previous conversation should still be here.
        # -------------------------------------------------

        if self.call_count == 3:
            # Previous assistant response must still exist.
            assert any(
                message.role == "assistant"
                and "hello.txt" in message.content
                for message in request.messages
            )

            # The new user follow-up must also be present.
            assert any(
                message.role == "user"
                and message.content == "What does it contain?"
                for message in request.messages
            )

            # Because previous context tells us that
            # "it" means hello.txt, request read_file.
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

        # -------------------------------------------------
        # CALL 4
        #
        # JARVIS should now have returned the REAL
        # contents of hello.txt.
        # -------------------------------------------------

        assert any(
            message.role == "tool"
            and "Hello from history test" in message.content
            for message in request.messages
        )

        return ModelResponse(
            text=(
                "It contains: "
                "Hello from history test"
            ),
            provider=self.name,
            model="test-model",
        )


# ---------------------------------------------------------
# TEST HELPER
# Build the REAL JARVIS tool/security pipeline
# ---------------------------------------------------------


def build_tool_service(
    workspace: Path,
    *,
    allow_read: bool,
) -> ToolService:
    """
    Build a real ToolService for our tests.

    We deliberately use the real:

        ToolRegistry
            ↓
        PermissionPolicy
            ↓
        ToolExecutor
            ↓
        Tools

    This makes the tests exercise the same security
    architecture as the real JARVIS application.
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


# ---------------------------------------------------------
# TEST 1
# Normal conversation
# ---------------------------------------------------------


def test_agent_returns_normal_model_response(
    tmp_path: Path,
) -> None:
    """
    Normal chat should work without requiring any tools.
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


# ---------------------------------------------------------
# TEST 2
# Multi-step agent inside one user request
# ---------------------------------------------------------


def test_agent_executes_multiple_tool_rounds(
    tmp_path: Path,
) -> None:
    """
    Verify:

        user request
            ↓
        list_directory
            ↓
        hello.txt
            ↓
        read_file
            ↓
        real contents
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

    # Exactly:
    #
    # 1. choose list_directory
    # 2. choose read_file
    # 3. final answer
    assert provider.call_count == 3


# ---------------------------------------------------------
# TEST 3
# Security / permissions
# ---------------------------------------------------------


def test_agent_cannot_bypass_permission_policy(
    tmp_path: Path,
) -> None:
    """
    Even if the AI requests a valid tool,
    JARVIS must reject execution when READ_FILE
    permission is disabled.
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


# ---------------------------------------------------------
# TEST 4
# Infinite-agent-loop protection
# ---------------------------------------------------------


def test_agent_stops_infinite_tool_loop(
    tmp_path: Path,
) -> None:
    """
    A broken or confused model must not be able
    to run tools forever.
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


# ---------------------------------------------------------
# TEST 5
# Conversation memory across separate user requests
# ---------------------------------------------------------


def test_agent_remembers_previous_user_request(
    tmp_path: Path,
) -> None:
    """
    Verify conversation history across TWO separate
    AgentService.run() calls.

    First request:

        "What files do I have?"

    Response:

        "You have hello.txt."

    Second request:

        "What does it contain?"

    JARVIS must understand that "it" means hello.txt
    because the previous conversation is preserved.
    """

    (
        tmp_path / "hello.txt"
    ).write_text(
        "Hello from history test",
        encoding="utf-8",
    )

    provider = ConversationHistoryProvider()

    agent = AgentService(
        model_provider=provider,
        tool_service=build_tool_service(
            tmp_path,
            allow_read=True,
        ),
    )

    # This same Conversation object is supplied to
    # BOTH separate agent requests.
    conversation = Conversation()

    # -------------------------------------------------
    # FIRST USER REQUEST
    # -------------------------------------------------

    first_answer = agent.run(
        "What files do I have?",
        conversation=conversation,
    )

    assert first_answer == "You have hello.txt."

    # Conversation should now contain history.
    assert len(conversation) > 0

    # -------------------------------------------------
    # SECOND USER REQUEST
    #
    # Notice that we do NOT say "hello.txt".
    #
    # We only say "it".
    # -------------------------------------------------

    second_answer = agent.run(
        "What does it contain?",
        conversation=conversation,
    )

    assert second_answer == (
        "It contains: "
        "Hello from history test"
    )

    # Expected model calls:
    #
    # 1. list_directory
    # 2. answer first question
    # 3. read_file based on previous context
    # 4. answer second question
    assert provider.call_count == 4