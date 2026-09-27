from pathlib import Path

from jarvis.bootstrap import build_application
from jarvis.core.config import JarvisSettings


def test_approved_scope_survives_application_restart(
    tmp_path: Path,
) -> None:
    """
    Simulate:

        start JARVIS
        approve Desktop
        close JARVIS
        start JARVIS again

    The approved Desktop scope must still exist.
    """

    workspace = tmp_path / "workspace"
    desktop = tmp_path / "Desktop"
    state_dir = tmp_path / "state"

    workspace.mkdir()
    desktop.mkdir()

    settings = JarvisSettings(
        workspace_dir=workspace,
        state_dir=state_dir,
        persist_filesystem_scopes=True,
        allow_read_file=True,
    )

    # -------------------------------------------------
    # First JARVIS process
    # -------------------------------------------------

    first_app = build_application(
        settings
    )

    first_app.add_filesystem_read_scope(
        desktop
    )

    assert desktop.resolve() in (
        first_app.filesystem_read_scopes()
    )

    # -------------------------------------------------
    # Simulate a complete restart by constructing an
    # entirely new JarvisApplication.
    # -------------------------------------------------

    second_app = build_application(
        settings
    )

    assert desktop.resolve() in (
        second_app.filesystem_read_scopes()
    )