from pathlib import Path

from jarvis.bootstrap import build_application
from jarvis.core.config import JarvisSettings
from jarvis.security.capabilities import Capability
from jarvis.security.permission_mode import PermissionMode
from jarvis.security.permission_mode_store import PermissionModeStore
from jarvis.security.policy import PermissionDecision


def test_permission_policy_can_change_at_runtime(
    tmp_path: Path,
) -> None:
    """
    Trusted application code should be able to change a
    capability between Ask, Allow, and Deny.
    """

    workspace = tmp_path / "workspace"

    workspace.mkdir()

    app = build_application(
        JarvisSettings(
            workspace_dir=workspace,
        )
    )

    assert (
        app.permission_decision(
            Capability.WRITE_FILE
        )
        is PermissionDecision.REQUIRE_CONFIRMATION
    )

    app.set_permission_mode(
        Capability.WRITE_FILE,
        PermissionMode.ALLOW_SESSION,
    )

    assert (
        app.permission_decision(
            Capability.WRITE_FILE
        )
        is PermissionDecision.ALLOW
    )

    app.set_permission_mode(
        Capability.WRITE_FILE,
        PermissionMode.DENY,
    )

    assert (
        app.permission_decision(
            Capability.WRITE_FILE
        )
        is PermissionDecision.DENY
    )


def test_always_allow_survives_restart(
    tmp_path: Path,
) -> None:
    """
    ALWAYS_ALLOW must persist across application restarts.
    """

    workspace = tmp_path / "workspace"
    state_dir = tmp_path / "state"

    workspace.mkdir()

    settings = JarvisSettings(
        workspace_dir=workspace,
        state_dir=state_dir,
        persist_permission_modes=True,
    )

    first_app = build_application(
        settings
    )

    first_app.set_permission_mode(
        Capability.WRITE_FILE,
        PermissionMode.ALWAYS_ALLOW,
    )

    second_app = build_application(
        settings
    )

    assert (
        second_app.permission_mode(
            Capability.WRITE_FILE
        )
        is PermissionMode.ALWAYS_ALLOW
    )

    assert (
        second_app.permission_decision(
            Capability.WRITE_FILE
        )
        is PermissionDecision.ALLOW
    )


def test_session_allow_returns_to_ask_after_restart(
    tmp_path: Path,
) -> None:
    """
    ALLOW_SESSION must disappear when JARVIS restarts.
    """

    workspace = tmp_path / "workspace"
    state_dir = tmp_path / "state"

    workspace.mkdir()

    settings = JarvisSettings(
        workspace_dir=workspace,
        state_dir=state_dir,
        persist_permission_modes=True,
    )

    first_app = build_application(
        settings
    )

    first_app.set_permission_mode(
        Capability.DELETE_FILE,
        PermissionMode.ALLOW_SESSION,
    )

    assert (
        first_app.permission_decision(
            Capability.DELETE_FILE
        )
        is PermissionDecision.ALLOW
    )

    second_app = build_application(
        settings
    )

    assert (
        second_app.permission_mode(
            Capability.DELETE_FILE
        )
        is PermissionMode.ASK
    )

    assert (
        second_app.permission_decision(
            Capability.DELETE_FILE
        )
        is PermissionDecision.REQUIRE_CONFIRMATION
    )


def test_permission_store_round_trip(
    tmp_path: Path,
) -> None:
    """
    Persistent modes should survive JSON serialization.
    """

    store = PermissionModeStore(
        tmp_path / "permission_modes.json"
    )

    store.save(
        {
            Capability.WRITE_FILE:
                PermissionMode.ALWAYS_ALLOW,

            Capability.DELETE_FILE:
                PermissionMode.DENY,
        }
    )

    loaded = store.load()

    assert loaded == {
        Capability.WRITE_FILE:
            PermissionMode.ALWAYS_ALLOW,

        Capability.DELETE_FILE:
            PermissionMode.DENY,
    }