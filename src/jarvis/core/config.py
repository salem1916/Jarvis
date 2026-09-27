import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_state_dir() -> Path:
    """
    Return JARVIS's private application-state directory.

    On Windows this normally becomes:

        %APPDATA%\\Jarvis

    Example:

        C:\\Users\\salem\\AppData\\Roaming\\Jarvis

    This is intentionally outside the Git repository.
    """

    appdata = os.environ.get(
        "APPDATA"
    )

    if appdata:
        return Path(
            appdata
        ) / "Jarvis"

    # Fallback for non-Windows development/testing
    # environments.
    return Path.home() / ".jarvis"


class JarvisSettings(BaseSettings):
    """
    Base JARVIS configuration.

    Important testing rule:

    filesystem-scope persistence is OFF by default here.

    Unit tests that construct JarvisSettings directly
    therefore never read or modify the user's real
    AppData permissions.
    """

    model_config = SettingsConfigDict(
        env_prefix="JARVIS_",
        extra="ignore",
    )

    workspace_dir: Path = Path(
        "workspace"
    )

    allow_read_file: bool = False
    allow_system_info: bool = False

    model_provider: str = "ollama"

    ollama_model: str = "qwen3.5:4b"

    ollama_base_url: str = (
        "http://127.0.0.1:11434"
    )

    # -------------------------------------------------
    # Persistent JARVIS application state
    # -------------------------------------------------

    state_dir: Path = Field(
        default_factory=_default_state_dir
    )

    # False for deterministic unit tests.
    #
    # The real runtime subclass below turns this on.
    persist_filesystem_scopes: bool = False


class _EnvJarvisSettings(JarvisSettings):
    """
    Real runtime settings.

    These read .env and enable persistent filesystem
    approvals by default.
    """

    persist_filesystem_scopes: bool = True

    model_config = SettingsConfigDict(
        env_prefix="JARVIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def load_settings() -> JarvisSettings:
    """
    Load the real JARVIS runtime configuration.
    """

    return _EnvJarvisSettings()