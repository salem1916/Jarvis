from pathlib import Path

from jarvis.security.capabilities import Capability
from jarvis.security.filesystem_scope import FilesystemScopePolicy
from jarvis.tools.list_filesystem_scopes import ListFilesystemScopesTool


def test_scope_tool_lists_workspace(
    tmp_path: Path,
) -> None:
    """
    The permanent workspace should always be visible
    to the filesystem-scope discovery tool.
    """

    workspace = tmp_path / "workspace"

    workspace.mkdir()

    policy = FilesystemScopePolicy(
        workspace
    )

    tool = ListFilesystemScopesTool(
        policy
    )

    result = tool.execute(
        {}
    )

    # Tool.execute() has the generic return type "object".
    #
    # Prove to Pyright that this specific tool returned
    # the list structure we expect before inspecting it.
    assert isinstance(
        result,
        list,
    )

    assert result == [
        {
            "path": str(
                workspace.resolve()
            ),
            "kind": "workspace",
        }
    ]


def test_scope_tool_lists_user_approved_folder(
    tmp_path: Path,
) -> None:
    """
    User-approved folders should appear as
    approved_folder entries.
    """

    workspace = tmp_path / "workspace"
    desktop = tmp_path / "Desktop"

    workspace.mkdir()
    desktop.mkdir()

    policy = FilesystemScopePolicy(
        workspace
    )

    policy.add_root(
        desktop
    )

    tool = ListFilesystemScopesTool(
        policy
    )

    result = tool.execute(
        {}
    )

    # Narrow the generic "object" return value
    # to the real list returned by this tool.
    assert isinstance(
        result,
        list,
    )

    assert {
        "path": str(
            desktop.resolve()
        ),
        "kind": "approved_folder",
    } in result


def test_scope_tool_requires_read_file_capability(
    tmp_path: Path,
) -> None:
    """
    Discovering approved filesystem locations is itself
    part of filesystem read access.
    """

    workspace = tmp_path / "workspace"

    workspace.mkdir()

    policy = FilesystemScopePolicy(
        workspace
    )

    tool = ListFilesystemScopesTool(
        policy
    )

    assert (
        tool.required_capability
        is Capability.READ_FILE
    )