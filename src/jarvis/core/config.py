from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class JarvisSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JARVIS_",
        extra="ignore",
    )

    workspace_dir: Path = Path("workspace")
    allow_read_file: bool = False


def load_settings() -> JarvisSettings:
    return JarvisSettings(
        _env_file=".env",
        _env_file_encoding="utf-8",
    )