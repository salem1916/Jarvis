from pathlib import Path

from jarvis.security.filesystem_scope_store import FilesystemScopeStore


def test_scope_store_saves_and_loads_folders(
    tmp_path: Path,
) -> None:
    """
    Explicitly approved folders should survive through
    the persistence store.
    """

    desktop = tmp_path / "Desktop"
    documents = tmp_path / "Documents"

    desktop.mkdir()
    documents.mkdir()

    store = FilesystemScopeStore(
        tmp_path / "state" / "filesystem_scopes.json"
    )

    store.save(
        [
            desktop,
            documents,
        ]
    )

    loaded = store.load()

    assert loaded == (
        desktop.resolve(),
        documents.resolve(),
    )


def test_scope_store_ignores_folder_that_no_longer_exists(
    tmp_path: Path,
) -> None:
    """
    Removing a previously approved directory outside JARVIS
    should not prevent JARVIS from starting.
    """

    desktop = tmp_path / "Desktop"

    desktop.mkdir()

    store = FilesystemScopeStore(
        tmp_path / "filesystem_scopes.json"
    )

    store.save(
        [
            desktop,
        ]
    )

    desktop.rmdir()

    assert store.load() == ()