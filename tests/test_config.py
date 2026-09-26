from pathlib import Path

from jarvis.core.config import JarvisSettings


def test_settings_have_safe_defaults():
    settings = JarvisSettings()

    assert settings.workspace_dir == Path("workspace")
    assert settings.allow_read_file is False


def test_settings_can_be_overridden():
    settings = JarvisSettings(
        workspace_dir=Path("test_workspace"),
        allow_read_file=True,
    )

    assert settings.workspace_dir == Path("test_workspace")
    assert settings.allow_read_file is True