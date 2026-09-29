import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_state_dir() -> Path:
    """
    Return JARVIS's private application-state directory.

    Windows example:

        C:\\Users\\salem\\AppData\\Roaming\\Jarvis
    """

    appdata = os.environ.get(
        "APPDATA"
    )

    if appdata:
        return Path(
            appdata
        ) / "Jarvis"

    return Path.home() / ".jarvis"


class JarvisSettings(BaseSettings):
    """
    Base JARVIS configuration.

    Persistence defaults to False here so unit tests never
    accidentally touch the user's real application state.
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

    # -------------------------------------------------
    # Legacy/default model bootstrap configuration.
    #
    # These remain useful as safe startup defaults while
    # RuntimeProfile becomes the user's real model-selection
    # source of truth.
    # -------------------------------------------------

    model_provider: str = "ollama"

    ollama_model: str = "qwen3.5:4b"

    ollama_base_url: str = (
        "http://127.0.0.1:11434"
    )

    state_dir: Path = Field(
        default_factory=_default_state_dir
    )

    persist_filesystem_scopes: bool = False

    persist_permission_modes: bool = False

    persist_runtime_profile: bool = False


class _EnvJarvisSettings(JarvisSettings):
    """
    Real JARVIS runtime configuration.

    User-approved scopes, permission modes, and runtime model
    choices persist by default in the desktop application.
    """

    persist_filesystem_scopes: bool = True

    persist_permission_modes: bool = True

    persist_runtime_profile: bool = True

    model_config = SettingsConfigDict(
        env_prefix="JARVIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def load_settings() -> JarvisSettings:
    """
    Load real runtime settings.
    """

    return _EnvJarvisSettings()