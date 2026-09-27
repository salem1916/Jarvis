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
from jarvis.tools.list_filesystem_scopes import ListFilesystemScopesTool
from jarvis.tools.read_file import ReadFileTool
from jarvis.tools.registry import ToolRegistry
from jarvis.tools.service import ToolService


class FilesystemScopeDiscoveryProvider(ModelProvider):
    """
    Fake model that reproduces the desired agent behavior.

    Model turn 1:
        discover approved filesystem scopes

    Model turn 2:
        notice that Desktop is approved
        request the absolute file path

    Model turn 3:
        return the real file contents
    """

    name = "test"

    def __init__(
        self,
        file_path: Path,
    ) -> None:
        self.file_path = file_path.resolve()
        self.call_count = 0

    def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        self.call_count += 1

        # -------------------------------------------------
        # First model turn:
        # discover which real folders JARVIS can access.
        # -------------------------------------------------

        if self.call_count == 1:
            tool_names = {
                tool.name
                for tool in request.tools
            }

            assert "list_filesystem_scopes" in tool_names
            assert "read_file" in tool_names

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

        # -------------------------------------------------
        # Second model turn:
        #
        # The tool result must show an approved Desktop.
        # -------------------------------------------------

        if self.call_count == 2:
            assert any(
                message.role == "tool"
                and "approved_folder" in message.content
                and "Desktop" in message.content
                for message in request.messages
            )

            return ModelResponse(
                text="",
                provider=self.name,
                model="test-model",
                tool_calls=[
                    ModelToolCall(
                        name="read_file",
                        arguments={
                            "path": str(
                                self.file_path
                            ),
                        },
                    )
                ],
            )

        # -------------------------------------------------
        # Third model turn:
        #
        # JARVIS must have read the actual external file.
        # -------------------------------------------------

        assert any(
            message.role == "tool"
            and "Learning from Desktop works" in message.content
            for message in request.messages
        )

        return ModelResponse(
            text="The file says: Learning from Desktop works",
            provider=self.name,
            model="test-model",
        )


def test_agent_discovers_scope_before_reading_external_file(
    tmp_path: Path,
) -> None:
    """
    Verify the full secure agent path:

        user asks about Desktop
            ↓
        list_filesystem_scopes
            ↓
        approved Desktop path
            ↓
        read_file with absolute path
            ↓
        real file contents
    """

    workspace = tmp_path / "workspace"
    desktop = tmp_path / "Desktop"

    workspace.mkdir()
    desktop.mkdir()

    learn_file = desktop / "learn.txt"

    learn_file.write_text(
        "Learning from Desktop works",
        encoding="utf-8",
    )

    scope_policy = FilesystemScopePolicy(
        workspace
    )

    scope_policy.add_root(
        desktop
    )

    registry = ToolRegistry()

    registry.register(
        ListFilesystemScopesTool(
            scope_policy
        )
    )

    registry.register(
        ReadFileTool(
            workspace,
            scope_policy=scope_policy,
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

    tool_service = ToolService(
        registry,
        executor,
    )

    provider = FilesystemScopeDiscoveryProvider(
        learn_file
    )

    agent = AgentService(
        model_provider=provider,
        tool_service=tool_service,
    )

    result = agent.run(
        "Read learn.txt on my Desktop."
    )

    assert result == (
        "The file says: "
        "Learning from Desktop works"
    )

    assert provider.call_count == 3