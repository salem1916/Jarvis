from pathlib import Path

import pytest

from jarvis.security.filesystem_scope import FilesystemScopePolicy


def test_workspace_is_allowed_by_default(
    tmp_path: Path,
) -> None:
    """
    The JARVIS workspace is always the first allowed
    filesystem scope.
    """

    workspace = tmp_path / "workspace"

    workspace.mkdir()

    policy = FilesystemScopePolicy(
        workspace
    )

    assert policy.allowed_roots == (
        workspace.resolve(),
    )


def test_relative_path_resolves_inside_workspace(
    tmp_path: Path,
) -> None:
    """
    Existing relative-path behavior must remain compatible.

    "hello.txt" means:

        workspace/hello.txt
    """

    workspace = tmp_path / "workspace"

    workspace.mkdir()

    file_path = workspace / "hello.txt"

    file_path.write_text(
        "hello",
        encoding="utf-8",
    )

    policy = FilesystemScopePolicy(
        workspace
    )

    resolved = policy.resolve_path(
        "hello.txt"
    )

    assert resolved == file_path.resolve()


def test_path_outside_allowed_scopes_is_rejected(
    tmp_path: Path,
) -> None:
    """
    READ_FILE capability alone must NOT mean unrestricted
    filesystem access.

    The resource must also be inside an approved scope.
    """

    workspace = tmp_path / "workspace"
    outside = tmp_path / "private"

    workspace.mkdir()
    outside.mkdir()

    secret = outside / "secret.txt"

    secret.write_text(
        "secret",
        encoding="utf-8",
    )

    policy = FilesystemScopePolicy(
        workspace
    )

    with pytest.raises(
        ValueError,
        match="outside the allowed filesystem scopes",
    ):
        policy.resolve_path(
            secret
        )


def test_additional_folder_can_be_granted(
    tmp_path: Path,
) -> None:
    """
    A user-approved external directory becomes readable
    after being added as a filesystem scope.
    """

    workspace = tmp_path / "workspace"
    documents = tmp_path / "Documents"

    workspace.mkdir()
    documents.mkdir()

    document = documents / "university.txt"

    document.write_text(
        "FH Dortmund",
        encoding="utf-8",
    )

    policy = FilesystemScopePolicy(
        workspace
    )

    policy.add_root(
        documents
    )

    assert policy.resolve_path(
        document
    ) == document.resolve()

    assert documents.resolve() in policy.allowed_roots


def test_external_scope_can_be_removed_but_workspace_cannot(
    tmp_path: Path,
) -> None:
    """
    User-granted scopes are reversible.

    The internal workspace remains permanently available
    as JARVIS's minimum filesystem sandbox.
    """

    workspace = tmp_path / "workspace"
    documents = tmp_path / "Documents"

    workspace.mkdir()
    documents.mkdir()

    policy = FilesystemScopePolicy(
        workspace
    )

    policy.add_root(
        documents
    )

    policy.remove_root(
        documents
    )

    assert documents.resolve() not in policy.allowed_roots

    with pytest.raises(
        ValueError,
        match="workspace scope cannot be removed",
    ):
        policy.remove_root(
            workspace
        )

def test_approved_folder_name_can_be_used_as_alias(
    tmp_path: Path,
) -> None:
    """
    If Desktop is an approved root:

        Desktop\\learn.txt

    should resolve to the real approved Desktop rather
    than workspace/Desktop.
    """

    workspace = tmp_path / "workspace"
    desktop = tmp_path / "Desktop"

    workspace.mkdir()
    desktop.mkdir()

    learn_file = desktop / "learn.txt"

    learn_file.write_text(
        "real desktop content",
        encoding="utf-8",
    )

    policy = FilesystemScopePolicy(
        workspace
    )

    policy.add_root(
        desktop
    )

    resolved = policy.resolve_path(
        Path("Desktop") / "learn.txt"
    )

    assert resolved == learn_file.resolve()


def test_ambiguous_scope_alias_is_rejected(
    tmp_path: Path,
) -> None:
    """
    If two approved roots have the same folder name,
    JARVIS must refuse to guess.
    """

    workspace = tmp_path / "workspace"

    first_parent = tmp_path / "first"
    second_parent = tmp_path / "second"

    first_desktop = first_parent / "Desktop"
    second_desktop = second_parent / "Desktop"

    workspace.mkdir()

    first_desktop.mkdir(
        parents=True
    )

    second_desktop.mkdir(
        parents=True
    )

    policy = FilesystemScopePolicy(
        workspace
    )

    policy.add_root(
        first_desktop
    )

    policy.add_root(
        second_desktop
    )

    with pytest.raises(
        ValueError,
        match="alias is ambiguous",
    ):
        policy.resolve_path(
            Path("Desktop") / "file.txt"
        )        