from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class JarvisSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JARVIS_",
        env_file=".env",
        extra="ignore",
    )

    workspace_dir: Path = Path("workspace")
    allow_read_file: bool = False