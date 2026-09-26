from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class JarvisSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JARVIS_",
        extra="ignore",
    )

    workspace_dir: Path = Path("workspace")
    allow_read_file: bool = False


class _EnvJarvisSettings(JarvisSettings):
    model_config = SettingsConfigDict(
        env_prefix="JARVIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def load_settings() -> JarvisSettings:
    return _EnvJarvisSettings()