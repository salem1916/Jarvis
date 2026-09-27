from pathlib import Path

from jarvis.core.agent_service import AgentService
from jarvis.models.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelToolCall,
)
from jarvis.security.capabilities import Capability
from jarvis.security.filesystem_scope import FilesystemScopePolicy
from jarvis.security.policy import PermissionPolicy
from jarvis.tools.executor import ToolExecutor
from jarvis.tools.list_directory import ListDirectoryTool
from jarvis.tools.list_filesystem_scopes import ListFilesystemScopesTool
from jarvis.tools.registry import ToolRegistry
from jarvis.tools.service import ToolService


class RecoveringProvider(ModelProvider):
    """
    Fake model that deliberately makes one bad tool call.

    Round 1:
        list a nonexistent folder

    Round 2:
        receive structured tool error
        discover approved scopes

    Round 3:
        return a successful final response

    This proves one model mistake no longer has to kill
    the entire agent request.
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
                        name="list_directory",
                        arguments={
                            "path": "MissingFolder",
                        },
                    )
                ],
            )

        if self.call_count == 2:
            # JARVIS should have returned a structured
            # recoverable error instead of raising it
            # outside the agent loop.
            assert any(
                message.role == "tool"
                and '"ok": false' in message.content
                and "list_filesystem_scopes"
                in message.content
                for message in request.messages
            )

            return ModelResponse(
                text="",
                provider=self.name,
                model="test-model",
                tool_calls=[
                    ModelToolCall(
                        name="list_filesystem_scopes",
                        arguments={},
                    )
                ],
            )

        assert any(
            message.role == "tool"
            and "workspace" in message.content
            for message in request.messages
        )

        return ModelResponse(
            text="I recovered from the incorrect path.",
            provider=self.name,
            model="test-model",
        )


def test_agent_can_recover_from_bad_filesystem_path(
    tmp_path: Path,
) -> None:
    """
    A recoverable path error should become another
    agent observation rather than ending the request.
    """

    workspace = tmp_path / "workspace"

    workspace.mkdir()

    scope_policy = FilesystemScopePolicy(
        workspace
    )

    registry = ToolRegistry()

    registry.register(
        ListDirectoryTool(
            workspace,
            scope_policy=scope_policy,
        )
    )

    registry.register(
        ListFilesystemScopesTool(
            scope_policy
        )
    )

    permission_policy = PermissionPolicy(
        allowed={
            Capability.READ_FILE,
        }
    )

    executor = ToolExecutor(
        permission_policy
    )

    service = ToolService(
        registry,
        executor,
    )

    provider = RecoveringProvider()

    agent = AgentService(
        model_provider=provider,
        tool_service=service,
    )

    result = agent.run(
        "List something on my computer."
    )

    assert result == (
        "I recovered from the incorrect path."
    )

    assert provider.call_count == 3